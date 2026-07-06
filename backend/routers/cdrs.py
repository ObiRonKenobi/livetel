import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import CDR
from schemas import CdrResponse, SipFlowResponse

router = APIRouter(prefix="/api", tags=["cdrs"])

_CALL_ID_RE = re.compile(r"^[a-f0-9]{6,32}$", re.I)


def _cdr_to_response(r: CDR) -> CdrResponse:
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

    # Dotted IPv4 fragments (e.g. 123.45 or full 123.45.67.89)
    if "." in term and any(ch.isdigit() for ch in term):
        clauses.extend([CDR.from_uri.ilike(like), CDR.to_uri.ilike(like)])

    return or_(*clauses)


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
        if _CALL_ID_RE.fullmatch(term):
            query = query.filter(CDR.call_id.ilike(f"{term.lower()}%"))
            limit = max(limit, 500)
        else:
            query = query.filter(_search_clause(term))
            limit = max(limit, 300)

    rows = query.order_by(CDR.id.desc()).limit(limit).all()
    return [_cdr_to_response(r) for r in rows]


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
    return SipFlowResponse(call_id=rows[0].call_id, events=[_cdr_to_response(r) for r in rows])
