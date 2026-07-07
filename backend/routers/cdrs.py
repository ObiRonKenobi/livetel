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

_HEX_RE = re.compile(r"^[a-f0-9]+$", re.I)
_CALL_ID_EXACT_RE = re.compile(r"^[a-f0-9]{16}$", re.I)
_alert_windows_cache: tuple[float, list[tuple[datetime, datetime, str]]] | None = None


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


def _build_call_status_map(call_ids: set[str]) -> dict[str, str]:
    live = active_call_ids()
    return {cid: ("active" if cid in live else "completed") for cid in call_ids}


def _alert_windows(db: Session) -> list[tuple[datetime, datetime, str]]:
    global _alert_windows_cache
    now = time.monotonic()
    ttl = settings.alert_windows_cache_seconds
    if _alert_windows_cache is not None and now - _alert_windows_cache[0] < ttl:
        return _alert_windows_cache[1]

    cutoff = datetime.utcnow() - timedelta(hours=24)
    alerts = (
        db.query(Alert.timestamp, Alert.severity)
        .filter(
            Alert.timestamp >= cutoff,
            not_(or_(Alert.type.like("AI_%"), Alert.type == "AI_error")),
        )
        .all()
    )
    windows = [
        (a.timestamp - timedelta(seconds=90), a.timestamp + timedelta(seconds=30), a.severity)
        for a in alerts
    ]
    _alert_windows_cache = (now, windows)
    return windows


def _alert_severity_for(ts: datetime, windows: list[tuple[datetime, datetime, str]]) -> str | None:
    best: str | None = None
    for start, end, sev in windows:
        if start <= ts <= end:
            if sev == "critical":
                return "critical"
            if best != "critical":
                best = sev
    return best


def _alert_severity_by_call_id(
    db: Session,
    call_ids: set[str],
    windows: list[tuple[datetime, datetime, str]],
) -> dict[str, str]:
    """Map call_id → severity when any leg falls inside an alert window."""
    if not call_ids or not windows:
        return {}
    earliest = min(start for start, _, _ in windows)
    rows = (
        db.query(CDR.call_id, CDR.timestamp)
        .filter(CDR.call_id.in_(call_ids), CDR.timestamp >= earliest)
        .all()
    )
    by_call: dict[str, str] = {}
    for call_id, ts in rows:
        sev = _alert_severity_for(ts, windows)
        if not sev:
            continue
        prev = by_call.get(call_id)
        if sev == "critical" or prev == "critical":
            by_call[call_id] = "critical"
        elif prev:
            by_call[call_id] = prev
        else:
            by_call[call_id] = sev
    return by_call


def _resolve_alert_severity(
    r: CDR,
    windows: list[tuple[datetime, datetime, str]],
    by_call: dict[str, str],
) -> str | None:
    direct = _alert_severity_for(r.timestamp, windows)
    if direct == "critical":
        return "critical"
    inherited = by_call.get(r.call_id)
    if direct:
        return direct
    return inherited


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
    cutoff = datetime.utcnow() - timedelta(hours=24)
    times = [r.timestamp for r in cdr_rows]
    alerts = (
        db.query(Alert)
        .filter(
            Alert.timestamp >= cutoff,
            not_(or_(Alert.type.like("AI_%"), Alert.type == "AI_error")),
        )
        .order_by(Alert.timestamp.desc())
        .all()
    )

    matched: list[CallFlowAlertInfo] = []
    for alert in alerts:
        window_start = alert.timestamp - timedelta(seconds=90)
        window_end = alert.timestamp + timedelta(seconds=30)
        if not any(window_start <= ts <= window_end for ts in times):
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
    status_map = _build_call_status_map(call_ids)
    windows = _alert_windows(db)
    alert_by_call = _alert_severity_by_call_id(db, call_ids, windows)

    items = [
        _cdr_to_response(
            r,
            call_status=status_map.get(r.call_id, "completed"),
            alert_severity=_resolve_alert_severity(r, windows, alert_by_call),
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
    status_map = _build_call_status_map(call_ids)
    windows = _alert_windows(db)
    alert_by_call = _alert_severity_by_call_id(db, call_ids, windows)

    items = [
        _cdr_to_response(
            r,
            call_status=status_map.get(r.call_id, "completed"),
            alert_severity=_resolve_alert_severity(r, windows, alert_by_call),
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
    status = "active" if cid in active_call_ids() else "completed"
    windows = _alert_windows(db)
    alert_by_call = _alert_severity_by_call_id(db, {cid}, windows)

    return SipFlowResponse(
        call_id=cid,
        events=[
            _cdr_to_response(
                r,
                call_status=status,
                alert_severity=_resolve_alert_severity(r, windows, alert_by_call),
            )
            for r in rows
        ],
        alerts=_alerts_for_call(db, rows),
    )
