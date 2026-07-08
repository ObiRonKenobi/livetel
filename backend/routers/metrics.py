import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import CDR
from routers.cdrs import _alert_tracker_error_codes, _open_alerts_cached
from schemas import MetricsHistoryPoint, MetricsHistoryResponse, MetricsResponse
from services.generator import active_call_count, avg_call_duration_sec

router = APIRouter(prefix="/api", tags=["metrics"])

_ESTABLISHED = and_(CDR.sip_method == "INVITE", CDR.sip_code == 200)
_BUCKET = func.strftime("%Y-%m-%d %H:%M", CDR.timestamp)

_history_cache: tuple[float, MetricsHistoryResponse] | None = None
_HISTORY_CACHE_SECONDS = 15


def _qos_averages(db: Session, cutoff: datetime) -> tuple[float, float, float, float] | None:
    row = (
        db.query(
            func.avg(CDR.latency),
            func.avg(CDR.jitter),
            func.avg(CDR.packet_loss),
            func.avg(CDR.mos),
        )
        .filter(CDR.timestamp >= cutoff, _ESTABLISHED)
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


def _history_points(db: Session) -> list[MetricsHistoryPoint]:
    bucket_min = settings.metrics_history_bucket_minutes
    window_min = settings.metrics_history_minutes
    n_buckets = window_min // bucket_min

    end = datetime.utcnow().replace(second=0, microsecond=0)
    start = end - timedelta(minutes=window_min - bucket_min)

    # Established INVITE/200 only — one group-by scan (avoid a second full-window pass).
    by_est = (
        db.query(
            _BUCKET.label("bucket"),
            func.avg(CDR.latency),
            func.avg(CDR.jitter),
            func.avg(CDR.packet_loss),
            func.avg(CDR.mos),
        )
        .filter(CDR.timestamp >= start, _ESTABLISHED)
        .group_by(_BUCKET)
        .all()
    )
    by_est_map = {r.bucket: r for r in by_est}

    points: list[MetricsHistoryPoint] = []
    for i in range(n_buckets):
        t = start + timedelta(minutes=i * bucket_min)
        key = t.strftime("%Y-%m-%d %H:%M")
        row = by_est_map.get(key)
        if row and row[1] is not None:
            points.append(
                MetricsHistoryPoint(
                    time=t.isoformat() + "Z",
                    avg_latency=round(float(row[1]), 1),
                    avg_jitter=round(float(row[2]), 1),
                    avg_packet_loss=round(float(row[3]), 2),
                    avg_mos=round(float(row[4]), 2),
                )
            )
        else:
            points.append(MetricsHistoryPoint(time=t.isoformat() + "Z"))
    return points


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(db: Session = Depends(get_db)) -> MetricsResponse:
    cutoff = datetime.utcnow() - timedelta(seconds=settings.metrics_window_seconds)
    averages = _qos_averages(db, cutoff)

    open_alerts = _open_alerts_cached(db)
    error_codes = _alert_tracker_error_codes(db, open_alerts)

    sip_rows = (
        db.query(CDR.sip_code, func.count())
        .filter(CDR.timestamp >= cutoff, CDR.sip_code >= 100)
        .group_by(CDR.sip_code)
        .all()
    )
    sip_codes = {str(code): count for code, count in sip_rows}

    if averages is None:
        return MetricsResponse(
            active_calls=active_call_count(),
            avg_call_duration_sec=round(avg_call_duration_sec(), 0),
            avg_latency=0.0,
            avg_jitter=0.0,
            avg_packet_loss=0.0,
            avg_mos=0.0,
            sip_codes=sip_codes,
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
        sip_codes=sip_codes,
        error_codes=error_codes,
    )


@router.get("/metrics/history", response_model=MetricsHistoryResponse)
def get_metrics_history(db: Session = Depends(get_db)) -> MetricsHistoryResponse:
    global _history_cache
    now_mono = time.monotonic()
    if _history_cache is not None and now_mono - _history_cache[0] < _HISTORY_CACHE_SECONDS:
        return _history_cache[1]

    response = MetricsHistoryResponse(
        points=_history_points(db),
        window_minutes=settings.metrics_history_minutes,
        bucket_minutes=settings.metrics_history_bucket_minutes,
    )
    _history_cache = (now_mono, response)
    return response
