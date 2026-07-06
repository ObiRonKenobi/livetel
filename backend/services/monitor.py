import logging
from datetime import datetime, timedelta

import requests
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Alert, CDR
from services.anomalies import ANOMALIES
from services.template_analysis import template_analysis

logger = logging.getLogger(__name__)

_last_ai_alert: dict[str, datetime] = {}


def _recent_cdrs(session: Session, window_seconds: int) -> list[CDR]:
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    return session.query(CDR).filter(CDR.timestamp >= cutoff).all()


def _aggregate(recent: list[CDR]) -> dict[str, float]:
    count = len(recent)
    if count == 0:
        return {}
    error_count = sum(1 for c in recent if c.sip_code >= 400)
    auth_count = sum(1 for c in recent if c.sip_code in (401, 403))
    timeout_count = sum(1 for c in recent if c.sip_code == 408)
    exhaust_count = sum(1 for c in recent if c.sip_code == 503)
    fraud_count = sum(1 for c in recent if "premium-route.xyz" in c.to_uri or "premium-route.xyz" in c.from_uri)
    intl_count = sum(1 for c in recent if any(p in c.to_uri for p in ("+447", "+491", "+331", "+813", "+861", "+234")))
    return {
        "avg_latency": sum(c.latency for c in recent) / count,
        "avg_jitter": sum(c.jitter for c in recent) / count,
        "avg_packet_loss": sum(c.packet_loss for c in recent) / count,
        "avg_mos": sum(c.mos for c in recent) / count,
        "sip_error_rate": (error_count / count) * 100,
        "auth_rate": (auth_count / count) * 100,
        "timeout_rate": (timeout_count / count) * 100,
        "exhaust_503_rate": (exhaust_count / count) * 100,
        "fraud_ratio": fraud_count / count,
        "intl_ratio": intl_count / count,
    }


def _detect_anomaly(data: dict[str, float]) -> str | None:
    """Return highest-severity matching anomaly key."""
    critical: list[str] = []
    warning: list[str] = []

    if data["exhaust_503_rate"] > 0.15 or (data["sip_error_rate"] > 35 and data["exhaust_503_rate"] > 0.08):
        critical.append("trunk_exhaustion")
    if data["sip_error_rate"] > 30 and data["exhaust_503_rate"] <= 0.15:
        critical.append("carrier_outage")
    if data["auth_rate"] > 12:
        critical.append("auth_failure")
    if data["fraud_ratio"] > 0.12:
        critical.append("toll_fraud")
    if data["timeout_rate"] > 18:
        warning.append("dns_sip_failure")
    if data["avg_packet_loss"] > 8:
        warning.append("one_way_audio")
    if data["avg_latency"] > 200 or data["avg_packet_loss"] > 5:
        warning.append("congestion")
    elif data["avg_latency"] > 140:
        warning.append("latency_spike")
    if data["avg_mos"] < 2.8 and data["avg_mos"] > 0:
        warning.append("mos_degradation")
    if data["intl_ratio"] > 0.25:
        warning.append("suspicious_international")

    if critical:
        return critical[0]
    if warning:
        return warning[0]
    return None


def _should_emit_ai_alert(anomaly: str) -> bool:
    now = datetime.utcnow()
    last = _last_ai_alert.get(anomaly)
    if last and (now - last).total_seconds() < settings.ai_alert_cooldown_seconds:
        return False
    _last_ai_alert[anomaly] = now
    return True


def _call_ollama(prompt: str) -> str:
    response = requests.post(
        settings.ollama_url,
        json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("response", "AI analysis unavailable")


def monitor_and_alert() -> None:
    with SessionLocal() as session:
        recent = _recent_cdrs(session, settings.metrics_window_seconds)
        if not recent:
            return

        data = _aggregate(recent)
        anomaly = _detect_anomaly(data)
        if not anomaly or not _should_emit_ai_alert(anomaly):
            return

        severity = ANOMALIES[anomaly].severity if anomaly in ANOMALIES else "warning"

        if settings.use_template_ai:
            ai_text = template_analysis(anomaly, data)
            session.add(Alert(type=f"AI_{anomaly}", severity=severity, details=ai_text))
            session.commit()
            logger.info("Template AI alert created for %s", anomaly)
            return

        prompt = f"""You are a VoIP network expert. The following metrics indicate a '{anomaly}' event:
- Avg latency: {data['avg_latency']:.1f} ms
- Avg jitter: {data['avg_jitter']:.1f} ms
- Avg packet loss: {data['avg_packet_loss']:.2f}%
- SIP error rate: {data['sip_error_rate']:.1f}%

Explain the root cause and suggest immediate mitigation steps. Keep response under 200 words."""

        try:
            ai_text = _call_ollama(prompt)
            session.add(Alert(type=f"AI_{anomaly}", severity=severity, details=ai_text))
            session.commit()
        except Exception as exc:
            logger.exception("Ollama call failed")
            session.add(Alert(type="AI_error", severity="critical", details=str(exc)))
            session.commit()


def check_ollama_health() -> bool:
    try:
        base = settings.ollama_url.rsplit("/api/", 1)[0]
        response = requests.get(f"{base}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False
