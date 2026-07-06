from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import CDR
from schemas import MetricsResponse
from services.generator import active_call_count, avg_call_duration_sec

router = APIRouter(prefix="/api", tags=["metrics"])


def _qos_averages(db: Session, cutoff: datetime) -> tuple[float, float, float, float] | None:
    established = and_(CDR.sip_method == "INVITE", CDR.sip_code == 200)
    row = (
        db.query(
            func.avg(CDR.latency),
            func.avg(CDR.jitter),
            func.avg(CDR.packet_loss),
            func.avg(CDR.mos),
        )
        .filter(CDR.timestamp >= cutoff, established)
        .one()
    )
    if row[0] is not None:
        return row

    row = (
        db.query(
            func.avg(CDR.latency),
            func.avg(CDR.jitter),
            func.avg(CDR.packet_loss),
            func.avg(CDR.mos),
        )
        .filter(CDR.timestamp >= cutoff)
        .one()
    )
    if row[0] is None:
        return None
    return row


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(db: Session = Depends(get_db)) -> MetricsResponse:
    cutoff = datetime.utcnow() - timedelta(seconds=settings.metrics_window_seconds)
    averages = _qos_averages(db, cutoff)

    error_rows = (
        db.query(CDR.sip_code, func.count())
        .filter(CDR.timestamp >= cutoff)
        .group_by(CDR.sip_code)
        .all()
    )
    error_codes = {str(code): count for code, count in error_rows}

    if averages is None:
        return MetricsResponse(
            active_calls=active_call_count(),
            avg_call_duration_sec=round(avg_call_duration_sec(), 0),
            avg_latency=0.0,
            avg_jitter=0.0,
            avg_packet_loss=0.0,
            avg_mos=0.0,
            error_codes=error_codes,
        )

    avg_latency, avg_jitter, avg_packet_loss, avg_mos = averages
    return MetricsResponse(
        active_calls=active_call_count(),
        avg_call_duration_sec=round(avg_call_duration_sec(), 0),
        avg_latency=round(float(avg_latency), 1),
        avg_jitter=round(float(avg_jitter), 1),
        avg_packet_loss=round(float(avg_packet_loss), 2),
        avg_mos=round(float(avg_mos), 2),
        error_codes=error_codes,
    )
