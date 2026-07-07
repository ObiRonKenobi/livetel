import logging
from datetime import datetime, timedelta

import requests
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Alert, CDR
from services.anomalies import ANOMALIES
from services.template_analysis import template_analysis

logger = logging.getLogger(__name__)

_last_alert: dict[str, datetime] = {}


def _aggregate_metrics(session: Session, cutoff: datetime) -> dict[str, float]:
    fraud_match = or_(
        CDR.to_uri.like("%premium-route.xyz%"),
        CDR.from_uri.like("%premium-route.xyz%"),
    )
    row = (
        session.query(
            func.count(CDR.id),
            func.avg(CDR.latency),
            func.avg(CDR.jitter),
            func.avg(CDR.packet_loss),
            func.avg(CDR.mos),
            func.sum(case((CDR.sip_code >= 400, 1), else_=0)),
            func.sum(case((CDR.sip_code.in_([401, 403]), 1), else_=0)),
            func.sum(case((CDR.sip_code == 408, 1), else_=0)),
            func.sum(case((CDR.sip_code == 503, 1), else_=0)),
            func.sum(case((fraud_match, 1), else_=0)),
        )
        .filter(CDR.timestamp >= cutoff)
        .one()
    )

    count = int(row[0] or 0)
    if count == 0:
        return {}

    error_count = int(row[5] or 0)
    auth_count = int(row[6] or 0)
    timeout_count = int(row[7] or 0)
    exhaust_count = int(row[8] or 0)
    fraud_count = int(row[9] or 0)

    return {
        "avg_latency": float(row[1] or 0),
        "avg_jitter": float(row[2] or 0),
        "avg_packet_loss": float(row[3] or 0),
        "avg_mos": float(row[4] or 0),
        "sip_error_rate": (error_count / count) * 100,
        "auth_rate": (auth_count / count) * 100,
        "timeout_rate": (timeout_count / count) * 100,
        "exhaust_503_rate": (exhaust_count / count) * 100,
        "fraud_ratio": fraud_count / count,
    }


def _detect_anomaly(data: dict[str, float]) -> str | None:
    """Return highest-severity matching SIP / softphone anomaly key."""
    critical: list[str] = []
    warning: list[str] = []

    if data["exhaust_503_rate"] > 0.15 or (data["sip_error_rate"] > 35 and data["exhaust_503_rate"] > 0.08):
        critical.append("sip_503_overload")
    if data["sip_error_rate"] > 30 and data["exhaust_503_rate"] <= 0.15:
        critical.append("sip_trunk_unreachable")
    if data["auth_rate"] > 12:
        critical.append("auth_failure")
    if data["fraud_ratio"] > 0.12:
        critical.append("toll_fraud")
    if data["timeout_rate"] > 18:
        warning.append("sip_dns_timeout")
    if data["avg_packet_loss"] > 8:
        warning.append("one_way_audio")
    if data["avg_packet_loss"] > 5:
        warning.append("rtp_packet_loss")
    elif data["avg_latency"] > 200:
        warning.append("rtp_packet_loss")
    if data["avg_latency"] > 140:
        warning.append("sip_latency_spike")
    if data["avg_mos"] < 2.8 and data["avg_mos"] > 0:
        warning.append("codec_quality_drop")
    if data["auth_rate"] > 6 and data["auth_rate"] <= 12:
        warning.append("softphone_registration_failure")

    if critical:
        return critical[0]
    if warning:
        return warning[0]
    return None


def _should_emit_alert(anomaly: str) -> bool:
    now = datetime.utcnow()
    last = _last_alert.get(anomaly)
    if last and (now - last).total_seconds() < settings.ai_alert_cooldown_seconds:
        return False
    _last_alert[anomaly] = now
    return True


def monitor_and_alert() -> None:
    cutoff = datetime.utcnow() - timedelta(seconds=settings.metrics_window_seconds)
    with SessionLocal() as session:
        data = _aggregate_metrics(session, cutoff)
        if not data:
            return

        anomaly = _detect_anomaly(data)
        if not anomaly or not _should_emit_alert(anomaly):
            return

        severity = ANOMALIES[anomaly].severity if anomaly in ANOMALIES else "warning"
        details = template_analysis(anomaly, data)
        session.add(Alert(type=anomaly, severity=severity, details=details))
        session.commit()
        try:
            from routers.cdrs import invalidate_alert_windows_cache

            invalidate_alert_windows_cache()
        except Exception:
            pass
        logger.info("SIP alert created for %s", anomaly)


def check_ollama_health() -> bool:
    try:
        base = settings.ollama_url.rsplit("/api/", 1)[0]
        response = requests.get(f"{base}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False
