from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import CDR
from schemas import CdrResponse

router = APIRouter(prefix="/api", tags=["cdrs"])


@router.get("/cdrs", response_model=list[CdrResponse])
def get_cdrs(
    db: Session = Depends(get_db),
    search: str = Query(default="", max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CdrResponse]:
    cutoff = datetime.utcnow() - timedelta(hours=settings.prune_hours)
    query = db.query(CDR).filter(CDR.timestamp >= cutoff)

    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                CDR.src.ilike(term),
                CDR.dst.ilike(term),
                cast(CDR.sip_code, String).ilike(term),
            )
        )

    rows = query.order_by(CDR.timestamp.desc()).limit(limit).all()
    return [
        CdrResponse(
            time=r.timestamp.isoformat(),
            src=r.src,
            dst=r.dst,
            duration=r.duration,
            mos=r.mos,
            latency=r.latency,
            jitter=r.jitter,
            packet_loss=r.packet_loss,
            sip_code=r.sip_code,
        )
        for r in rows
    ]
