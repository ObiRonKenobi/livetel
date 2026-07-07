import re
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, and_, cast, not_, or_
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Alert, CDR
from schemas import CallFlowAlertInfo, CdrListResponse, CdrResponse, SipFlowResponse
from services.anomalies import ANOMALIES, LEGACY_KEY_MAP
from services.generator import active_call_ids
from services.template_analysis import template_mitigation, template_root_cause

router = APIRouter(prefix="/api", tags=["cdrs"])

MAX_CDR_PAGES = 10
CDR_PAGE_SIZE = 100
MAX_WINDOW_PAGE_SIZE = 500
ALERT_CORRELATION_BEFORE_SECONDS = 150
ALERT_CORRELATION_AFTER_SECONDS = 45

_HEX_RE = re.compile(r"^[a-f0-9]+$", re.I)
_CALL_ID_EXACT_RE = re.compile(r"^[a-f0-9]{16}$", re.I)
_open_alerts_cache: tuple[float, list[Alert]] | None = None


def _like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_pattern(term: str) -> str:
    return f"%{_like_escape(term.strip())}%"


def _normalize_call_id(raw: str) -> str:
    cid = raw.strip().lower()
    if not _HEX_RE.fullmatch(cid) or len(cid) < 6 or len(cid) > 16:
        raise HTTPException(status_code=400, detail="call_id must be 6–16 hex characters")
    return cid


def _is_call_id_search(term: str) -> bool:
    """Phone numbers are all digits (≤11); call IDs are 16-char hex (often include a-f)."""
    t = term.strip().lower()
    if not _HEX_RE.fullmatch(t):
        return False
    if any(c in "abcdef" for c in t):
        return len(t) >= 6
    return len(t) >= 12


def _cdr_to_response(
    r: CDR,
    *,
    call_status: str = "completed",
    alert_severity: str | None = None,
) -> CdrResponse:
    return CdrResponse(
        id=r.id,
        time=r.timestamp.isoformat() + "Z",
        call_id=r.call_id,
        direction=r.direction,
        sip_method=r.sip_method,
        from_uri=r.from_uri,
        to_uri=r.to_uri,
        duration=r.duration,
        mos=r.mos,
        latency=r.latency,
        jitter=r.jitter,
        packet_loss=r.packet_loss,
        sip_code=r.sip_code,
        leg=r.leg,
        call_status=call_status,
        alert_severity=alert_severity,
    )


def _search_clause(raw: str):
    """Match call IDs, URIs, IPs, phone digits (+ optional), SIP method/code, direction."""
    term = raw.strip()
    like = _like_pattern(term)
    clauses = [
        CDR.from_uri.ilike(like, escape="\\"),
        CDR.to_uri.ilike(like, escape="\\"),
        CDR.call_id.ilike(like, escape="\\"),
        CDR.direction.ilike(like, escape="\\"),
        CDR.sip_method.ilike(like, escape="\\"),
        cast(CDR.sip_code, String).ilike(like, escape="\\"),
    ]

    if term.startswith("+"):
        no_plus = term[1:]
        if no_plus:
            digits_like = _like_pattern(no_plus)
            clauses.extend([
                CDR.from_uri.ilike(digits_like, escape="\\"),
                CDR.to_uri.ilike(digits_like, escape="\\"),
            ])

    digits = "".join(c for c in term if c.isdigit())
    if digits and len(digits) >= 4:
        digits_like = _like_pattern(digits)
        clauses.extend([
            CDR.from_uri.ilike(digits_like, escape="\\"),
            CDR.to_uri.ilike(digits_like, escape="\\"),
        ])

    if "." in term and any(ch.isdigit() for ch in term):
        clauses.extend([
            CDR.from_uri.ilike(like, escape="\\"),
            CDR.to_uri.ilike(like, escape="\\"),
        ])

    return or_(*clauses)


_AUTH_CHALLENGE_CODES = {401, 407}


def _call_flow_phase(status: str, rows: list[CDR]) -> str:
    """UI phase for SIP ladder — in-progress calls lack BYE until teardown."""
    has_bye = any(r.sip_method == "BYE" for r in rows)
    has_200 = any(r.sip_method == "INVITE" and r.sip_code == 200 for r in rows)
    has_terminal_fail = any(
        (r.sip_method == "INVITE" and r.sip_code >= 400 and r.sip_code not in _AUTH_CHALLENGE_CODES)
        or (r.sip_method == "CANCEL" and r.sip_code >= 400)
        for r in rows
    )
    if has_bye:
        return "completed"
    if has_terminal_fail:
        return "failed"
    if status == "active":
        return "active" if has_200 else "ringing"
    if status == "failed":
        return "failed"
    return "completed"


def _call_dispositions(db: Session, call_ids: set[str]) -> dict[str, str]:
    """active = live or ringing in generator; failed = terminal INVITE/CANCEL error; else completed."""
    if not call_ids:
        return {}
    live = active_call_ids()
    result: dict[str, str] = {}
    remaining: set[str] = set()
    for cid in call_ids:
        if cid in live:
            result[cid] = "active"
        else:
            remaining.add(cid)
    if not remaining:
        return result

    rows = (
        db.query(CDR.call_id, CDR.sip_method, CDR.sip_code)
        .filter(CDR.call_id.in_(remaining))
        .all()
    )
    invite_codes: dict[str, list[int]] = {}
    has_bye: set[str] = set()
    has_cancel_fail: set[str] = set()
    for call_id, method, code in rows:
        if method == "INVITE":
            invite_codes.setdefault(call_id, []).append(code)
        elif method == "BYE":
            has_bye.add(call_id)
        elif method == "CANCEL" and code >= 400:
            has_cancel_fail.add(call_id)

    for cid in remaining:
        codes = invite_codes.get(cid, [])
        if cid in has_bye or any(c == 200 for c in codes):
            result[cid] = "completed"
        elif cid in has_cancel_fail or any(
            c >= 400 and c not in _AUTH_CHALLENGE_CODES for c in codes
        ):
            result[cid] = "failed"
        else:
            result[cid] = "completed"
    return result


def _correlation_window(alert: Alert) -> tuple[datetime, datetime]:
    """Fixed burst window around alert creation (matches alert context API)."""
    start = alert.timestamp - timedelta(seconds=ALERT_CORRELATION_BEFORE_SECONDS)
    end = alert.timestamp + timedelta(seconds=ALERT_CORRELATION_AFTER_SECONDS)
    return start, end


def _cdr_matches_anomaly(cdr: CDR, alert_type: str) -> bool:
    """True when this CDR leg looks like a symptom of the alert type."""
    t = _normalize_alert_type(alert_type)
    code = cdr.sip_code
    if t == "sip_503_overload":
        return cdr.sip_method == "INVITE" and code == 503
    if t == "sip_trunk_unreachable":
        return cdr.sip_method == "INVITE" and code in (503, 408)
    if t == "auth_failure":
        return cdr.sip_method == "INVITE" and code in (401, 403)
    if t == "sip_dns_timeout":
        return cdr.sip_method == "INVITE" and code == 408
    if t == "toll_fraud":
        uris = f"{cdr.from_uri or ''} {cdr.to_uri or ''}"
        return "premium-route.xyz" in uris
    if t == "rtp_packet_loss":
        return cdr.packet_loss > 5 or cdr.jitter > 30
    if t == "one_way_audio":
        return cdr.packet_loss > 8
    if t == "sip_latency_spike":
        return cdr.latency > 140
    if t == "codec_quality_drop":
        return 0 < cdr.mos < 3.0
    if t == "softphone_registration_failure":
        return cdr.sip_method == "REGISTER" and code in (401, 403)
    return False


def _cdr_alert_severity(cdr: CDR, open_alerts: list[Alert]) -> str | None:
    """Per-row severity: open alert whose burst window contains this leg and matches its type."""
    best: str | None = None
    for alert in open_alerts:
        start, end = _correlation_window(alert)
        if not (start <= cdr.timestamp <= end):
            continue
        if not _cdr_matches_anomaly(cdr, alert.type):
            continue
        sev = alert.severity if alert.severity in ("critical", "warning") else "warning"
        if sev == "critical":
            return "critical"
        if best != "critical":
            best = sev
    return best


def _alert_severities_for_rows(rows: list[CDR], open_alerts: list[Alert]) -> dict[int, str | None]:
    """Batch alert icons for a CDR page — same rules as _cdr_alert_severity."""
    if not rows or not open_alerts:
        return {r.id: None for r in rows}
    return {r.id: _cdr_alert_severity(r, open_alerts) for r in rows}


def _fetch_open_alerts(db: Session) -> list[Alert]:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    return (
        db.query(Alert)
        .filter(
            Alert.timestamp >= cutoff,
            Alert.dismissed_status.is_(None),
            not_(or_(Alert.type.like("AI_%"), Alert.type == "AI_error")),
        )
        .all()
    )


def _open_alerts_cached(db: Session) -> list[Alert]:
    global _open_alerts_cache
    now_mono = time.monotonic()
    ttl = settings.alert_windows_cache_seconds
    if _open_alerts_cache is not None and now_mono - _open_alerts_cache[0] < ttl:
        return _open_alerts_cache[1]
    open_alerts = _fetch_open_alerts(db)
    _open_alerts_cache = (now_mono, open_alerts)
    return open_alerts


def invalidate_alert_windows_cache() -> None:
    global _open_alerts_cache
    _open_alerts_cache = None


def _alert_summary(details: str) -> str:
    idx = details.find("Root cause:")
    return (details[:idx] if idx >= 0 else details).strip()


def _parse_alert_details(details: str) -> tuple[str, str]:
    root = ""
    mit = ""
    if "Root cause:" in details:
        after = details.split("Root cause:", 1)[1]
        if "Immediate mitigation:" in after:
            root, mit = after.split("Immediate mitigation:", 1)
        else:
            root = after
    return root.strip(), mit.strip()


def _normalize_alert_type(alert_type: str) -> str:
    base = alert_type.removeprefix("AI_")
    return LEGACY_KEY_MAP.get(base, base)


def _alerts_for_call(db: Session, cdr_rows: list[CDR]) -> list[CallFlowAlertInfo]:
    if not cdr_rows:
        return []
    t_min = min(r.timestamp for r in cdr_rows)
    t_max = max(r.timestamp for r in cdr_rows)
    alerts = (
        db.query(Alert)
        .filter(
            Alert.timestamp >= t_min - timedelta(seconds=ALERT_CORRELATION_BEFORE_SECONDS),
            Alert.timestamp <= t_max + timedelta(seconds=ALERT_CORRELATION_AFTER_SECONDS),
            not_(or_(Alert.type.like("AI_%"), Alert.type == "AI_error")),
        )
        .order_by(Alert.timestamp.desc())
        .all()
    )

    matched: list[CallFlowAlertInfo] = []
    for alert in alerts:
        window_start, window_end = _correlation_window(alert)
        if not any(
            window_start <= r.timestamp <= window_end and _cdr_matches_anomaly(r, alert.type)
            for r in cdr_rows
        ):
            continue

        root, mit = _parse_alert_details(alert.details)
        if not root:
            base_type = _normalize_alert_type(alert.type)
            meta = ANOMALIES.get(base_type)
            label = meta.label if meta else base_type.replace("_", " ").title()
            root = template_root_cause(base_type, label)
        if not mit:
            mit = template_mitigation(_normalize_alert_type(alert.type))

        matched.append(
            CallFlowAlertInfo(
                id=alert.id,
                time=alert.timestamp.isoformat() + "Z",
                type=alert.type,
                severity=alert.severity,
                summary=_alert_summary(alert.details),
                root_cause=root,
                mitigation=mit,
            )
        )
    return matched


def _get_window_cdrs(
    db: Session,
    *,
    sip_code: int | None,
    window_seconds: int,
    page: int,
    page_size: int,
) -> CdrListResponse:
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    query = db.query(CDR).filter(CDR.timestamp >= cutoff)
    if sip_code is not None:
        query = query.filter(CDR.sip_code == sip_code)

    total_count = query.count()
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    safe_page = min(max(1, page), total_pages)
    offset = (safe_page - 1) * page_size

    rows = query.order_by(CDR.timestamp.desc(), CDR.id.desc()).offset(offset).limit(page_size).all()

    call_ids = {r.call_id for r in rows}
    status_map = _call_dispositions(db, call_ids)
    open_alerts = _open_alerts_cached(db)
    severities = _alert_severities_for_rows(rows, open_alerts)

    items = [
        _cdr_to_response(
            r,
            call_status=status_map.get(r.call_id, "completed"),
            alert_severity=severities.get(r.id),
        )
        for r in rows
    ]

    return CdrListResponse(
        items=items,
        page=safe_page,
        page_size=page_size,
        total_pages=total_pages,
        total_count=total_count,
    )


@router.get("/cdrs", response_model=CdrListResponse)
def get_cdrs(
    db: Session = Depends(get_db),
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=CDR_PAGE_SIZE, ge=1, le=MAX_WINDOW_PAGE_SIZE),
    sip_code: int | None = Query(default=None, ge=100, le=699),
    window_seconds: int | None = Query(default=None, ge=1, le=3600),
) -> CdrListResponse:
    if window_seconds is not None:
        return _get_window_cdrs(
            db,
            sip_code=sip_code,
            window_seconds=window_seconds,
            page=page,
            page_size=min(page_size, MAX_WINDOW_PAGE_SIZE),
        )

    cutoff = datetime.utcnow() - timedelta(hours=settings.prune_hours)
    query = db.query(CDR).filter(CDR.timestamp >= cutoff)

    term = search.strip()
    if term:
        if _is_call_id_search(term):
            query = query.filter(CDR.call_id.ilike(f"{_like_escape(term.lower())}%", escape="\\"))
        else:
            query = query.filter(_search_clause(term))

    max_browsable = page_size * MAX_CDR_PAGES
    total_in_db = query.count() if term else max_browsable
    total_count = min(total_in_db, max_browsable)
    total_pages = MAX_CDR_PAGES
    safe_page = min(max(1, page), MAX_CDR_PAGES)
    safe_page_size = min(page_size, CDR_PAGE_SIZE)
    offset = (safe_page - 1) * safe_page_size

    rows = query.order_by(CDR.id.desc()).offset(offset).limit(safe_page_size).all()

    call_ids = {r.call_id for r in rows}
    status_map = _call_dispositions(db, call_ids)
    open_alerts = _open_alerts_cached(db)
    severities = _alert_severities_for_rows(rows, open_alerts)

    items = [
        _cdr_to_response(
            r,
            call_status=status_map.get(r.call_id, "completed"),
            alert_severity=severities.get(r.id),
        )
        for r in rows
    ]

    return CdrListResponse(
        items=items,
        page=safe_page,
        page_size=safe_page_size,
        total_pages=total_pages,
        total_count=total_count,
    )


@router.get("/calls/{call_id}", response_model=SipFlowResponse)
def get_call_flow(call_id: str, db: Session = Depends(get_db)) -> SipFlowResponse:
    cid_query = _normalize_call_id(call_id)
    if _CALL_ID_EXACT_RE.fullmatch(cid_query):
        rows = (
            db.query(CDR)
            .filter(CDR.call_id == cid_query)
            .order_by(CDR.timestamp.asc(), CDR.leg.asc(), CDR.id.asc())
            .all()
        )
    else:
        rows = (
            db.query(CDR)
            .filter(CDR.call_id.ilike(f"{_like_escape(cid_query)}%", escape="\\"))
            .order_by(CDR.timestamp.asc(), CDR.leg.asc(), CDR.id.asc())
            .all()
        )
    if not rows:
        raise HTTPException(status_code=404, detail="Call not found")

    cid = rows[0].call_id
    status = _call_dispositions(db, {cid}).get(cid, "completed")
    phase = _call_flow_phase(status, rows)
    open_alerts = _open_alerts_cached(db)
    severities = _alert_severities_for_rows(rows, open_alerts)

    return SipFlowResponse(
        call_id=cid,
        call_phase=phase,
        events=[
            _cdr_to_response(
                r,
                call_status=status,
                alert_severity=severities.get(r.id),
            )
            for r in rows
        ],
        alerts=_alerts_for_call(db, rows),
    )
