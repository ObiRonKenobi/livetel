import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, not_, or_
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Alert, CDR
from schemas import CdrResponse, SipFlowResponse
from services.generator import active_call_ids

router = APIRouter(prefix="/api", tags=["cdrs"])

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
        time=r.timestamp.isoformat(),
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


@router.get("/cdrs", response_model=list[CdrResponse])
def get_cdrs(
    db: Session = Depends(get_db),
    search: str = Query(default="", max_length=100),
    limit: int = Query(default=150, ge=1, le=500),
    before_id: int | None = Query(default=None),
) -> list[CdrResponse]:
    cutoff = datetime.utcnow() - timedelta(hours=settings.prune_hours)
    query = db.query(CDR).filter(CDR.timestamp >= cutoff)

    if before_id is not None:
        query = query.filter(CDR.id < before_id)

    term = search.strip()
    if term:
        if _is_call_id_search(term):
            query = query.filter(CDR.call_id.ilike(f"{term.lower()}%"))
            limit = max(limit, 500)
        else:
            query = query.filter(_search_clause(term))
            limit = max(limit, 300)

    rows = query.order_by(CDR.id.desc()).limit(limit).all()
    if not rows:
        return []

    call_ids = {r.call_id for r in rows}
    status_map = _build_call_status_map(call_ids)
    windows = _alert_windows(db)

    return [
        _cdr_to_response(
            r,
            call_status=status_map.get(r.call_id, "completed"),
            alert_severity=_alert_severity_for(r.timestamp, windows),
        )
        for r in rows
    ]


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

    return SipFlowResponse(
        call_id=cid,
        events=[
            _cdr_to_response(
                r,
                call_status=status,
                alert_severity=_alert_severity_for(r.timestamp, windows),
            )
            for r in rows
        ],
    )
