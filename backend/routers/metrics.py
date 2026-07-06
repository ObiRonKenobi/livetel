from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import CDR
from schemas import MetricsResponse

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(db: Session = Depends(get_db)) -> MetricsResponse:
    cutoff = datetime.utcnow() - timedelta(seconds=settings.metrics_window_seconds)
    recent = db.query(CDR).filter(CDR.timestamp >= cutoff).all()

    if not recent:
        return MetricsResponse(
            active_calls=0,
            avg_latency=0.0,
            avg_jitter=0.0,
            avg_packet_loss=0.0,
            avg_mos=0.0,
            error_codes={},
        )

    error_codes: dict[str, int] = {}
    for cdr in recent:
        key = str(cdr.sip_code)
        error_codes[key] = error_codes.get(key, 0) + 1

    count = len(recent)
    return MetricsResponse(
        active_calls=count,
        avg_latency=round(sum(c.latency for c in recent) / count, 1),
        avg_jitter=round(sum(c.jitter for c in recent) / count, 1),
        avg_packet_loss=round(sum(c.packet_loss for c in recent) / count, 2),
        avg_mos=round(sum(c.mos for c in recent) / count, 2),
        error_codes=error_codes,
    )
