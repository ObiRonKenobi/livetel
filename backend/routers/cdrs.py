from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import CDR
from schemas import CdrResponse, SipFlowResponse

router = APIRouter(prefix="/api", tags=["cdrs"])


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

    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                CDR.from_uri.ilike(term),
                CDR.to_uri.ilike(term),
                CDR.call_id.ilike(term),
                CDR.direction.ilike(term),
                cast(CDR.sip_code, String).ilike(term),
            )
        )

    rows = query.order_by(CDR.id.desc()).limit(limit).all()
    return [_cdr_to_response(r) for r in rows]


@router.get("/calls/{call_id}", response_model=SipFlowResponse)
def get_call_flow(call_id: str, db: Session = Depends(get_db)) -> SipFlowResponse:
    rows = (
        db.query(CDR)
        .filter(CDR.call_id == call_id)
        .order_by(CDR.timestamp.asc(), CDR.leg.asc(), CDR.id.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Call not found")
    return SipFlowResponse(call_id=call_id, events=[_cdr_to_response(r) for r in rows])
