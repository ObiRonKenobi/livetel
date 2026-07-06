import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, and_, cast, not_, or_
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Alert, CDR
from schemas import CdrListResponse, CdrResponse, SipFlowResponse
from services.generator import active_call_ids

router = APIRouter(prefix="/api", tags=["cdrs"])

MAX_CDR_PAGES = 10
CDR_PAGE_SIZE = 100

_HEX_RE = re.compile(r"^[a-f0-9]+$", re.I)


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
    like = f"%{term}%"
    clauses = [
        CDR.from_uri.ilike(like),
        CDR.to_uri.ilike(like),
        CDR.call_id.ilike(like),
        CDR.direction.ilike(like),
        CDR.sip_method.ilike(like),
        cast(CDR.sip_code, String).ilike(like),
    ]

    if term.startswith("+"):
        no_plus = term[1:]
        if no_plus:
            clauses.extend([CDR.from_uri.ilike(f"%{no_plus}%"), CDR.to_uri.ilike(f"%{no_plus}%")])

    digits = "".join(c for c in term if c.isdigit())
    if digits and len(digits) >= 4:
        clauses.extend([CDR.from_uri.ilike(f"%{digits}%"), CDR.to_uri.ilike(f"%{digits}%")])

    if "." in term and any(ch.isdigit() for ch in term):
        clauses.extend([CDR.from_uri.ilike(like), CDR.to_uri.ilike(like)])

    return or_(*clauses)


def _build_call_status_map(call_ids: set[str]) -> dict[str, str]:
    live = active_call_ids()
    return {cid: ("active" if cid in live else "completed") for cid in call_ids}


def _alert_windows(db: Session) -> list[tuple[datetime, datetime, str]]:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    alerts = (
        db.query(Alert.timestamp, Alert.severity)
        .filter(
            Alert.timestamp >= cutoff,
            not_(or_(Alert.type.like("AI_%"), Alert.type == "AI_error")),
        )
        .all()
    )
    return [
        (a.timestamp - timedelta(seconds=90), a.timestamp + timedelta(seconds=30), a.severity)
        for a in alerts
    ]


def _alert_severity_for(ts: datetime, windows: list[tuple[datetime, datetime, str]]) -> str | None:
    best: str | None = None
    for start, end, sev in windows:
        if start <= ts <= end:
            if sev == "critical":
                return "critical"
            if best != "critical":
                best = sev
    return best


def _fetch_alert_correlated_cdrs(db: Session, base_cutoff: datetime) -> list[CDR]:
    windows = _alert_windows(db)
    if not windows:
        return []
    time_filters = [
        and_(CDR.timestamp >= max(start, base_cutoff), CDR.timestamp <= end)
        for start, end, _ in windows
    ]
    return (
        db.query(CDR)
        .filter(CDR.timestamp >= base_cutoff, or_(*time_filters))
        .order_by(CDR.id.desc())
        .all()
    )


def _alert_severity_by_call_id(
    db: Session,
    base_cutoff: datetime,
    windows: list[tuple[datetime, datetime, str]],
) -> dict[str, str]:
    """Map call_id → severity when any leg falls inside an alert window."""
    by_call: dict[str, str] = {}
    for r in _fetch_alert_correlated_cdrs(db, base_cutoff):
        sev = _alert_severity_for(r.timestamp, windows)
        if not sev:
            continue
        prev = by_call.get(r.call_id)
        if sev == "critical" or prev == "critical":
            by_call[r.call_id] = "critical"
        elif prev:
            by_call[r.call_id] = prev
        else:
            by_call[r.call_id] = sev
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


@router.get("/cdrs", response_model=CdrListResponse)
def get_cdrs(
    db: Session = Depends(get_db),
    search: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=MAX_CDR_PAGES),
    page_size: int = Query(default=CDR_PAGE_SIZE, ge=1, le=CDR_PAGE_SIZE),
) -> CdrListResponse:
    cutoff = datetime.utcnow() - timedelta(hours=settings.prune_hours)
    query = db.query(CDR).filter(CDR.timestamp >= cutoff)

    term = search.strip()
    if term:
        if _is_call_id_search(term):
            query = query.filter(CDR.call_id.ilike(f"{term.lower()}%"))
        else:
            query = query.filter(_search_clause(term))

    total_in_db = query.count()
    max_browsable = page_size * MAX_CDR_PAGES
    total_count = min(total_in_db, max_browsable)
    total_pages = max(1, min(MAX_CDR_PAGES, (total_in_db + page_size - 1) // page_size))
    safe_page = min(page, total_pages)
    offset = (safe_page - 1) * page_size

    rows = query.order_by(CDR.id.desc()).offset(offset).limit(page_size).all()

    call_ids = {r.call_id for r in rows}
    status_map = _build_call_status_map(call_ids)
    windows = _alert_windows(db)
    alert_by_call = _alert_severity_by_call_id(db, cutoff, windows)

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


@router.get("/calls/{call_id}", response_model=SipFlowResponse)
def get_call_flow(call_id: str, db: Session = Depends(get_db)) -> SipFlowResponse:
    rows = (
        db.query(CDR)
        .filter(CDR.call_id.ilike(call_id.strip().lower()))
        .order_by(CDR.timestamp.asc(), CDR.leg.asc(), CDR.id.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Call not found")

    cid = rows[0].call_id
    status = "active" if cid in active_call_ids() else "completed"
    windows = _alert_windows(db)
    alert_by_call = _alert_severity_by_call_id(db, datetime.utcnow() - timedelta(hours=settings.prune_hours), windows)

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
    )
