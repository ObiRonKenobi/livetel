import logging
from datetime import datetime, timedelta

import requests
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Alert, CDR

logger = logging.getLogger(__name__)

_last_ai_alert: dict[str, datetime] = {}


def _recent_cdrs(session: Session, window_seconds: int) -> list[CDR]:
    cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
    return session.query(CDR).filter(CDR.timestamp >= cutoff).all()


def _aggregate(recent: list[CDR]) -> dict[str, float]:
    count = len(recent)
    error_count = sum(1 for c in recent if c.sip_code >= 400)
    return {
        "avg_latency": sum(c.latency for c in recent) / count,
        "avg_jitter": sum(c.jitter for c in recent) / count,
        "avg_packet_loss": sum(c.packet_loss for c in recent) / count,
        "sip_error_rate": (error_count / count) * 100,
        "unusual_dest_ratio": sum(1 for c in recent if c.dst.startswith("XYZ")) / count,
    }


def _detect_anomaly(data: dict[str, float]) -> str | None:
    if data["avg_latency"] > 200 or data["avg_packet_loss"] > 5:
        return "congestion"
    if data["sip_error_rate"] > 30:
        return "carrier_outage"
    if data["unusual_dest_ratio"] > 0.2:
        return "toll_fraud"
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

        prompt = f"""You are a VoIP network expert. The following metrics indicate a '{anomaly}' event:
- Avg latency: {data['avg_latency']:.1f} ms
- Avg jitter: {data['avg_jitter']:.1f} ms
- Avg packet loss: {data['avg_packet_loss']:.2f}%
- SIP error rate: {data['sip_error_rate']:.1f}%
- Unusual destination call ratio: {data['unusual_dest_ratio']:.2%}

Explain the root cause and suggest immediate mitigation steps. Keep response under 200 words."""

        try:
            ai_text = _call_ollama(prompt)
            session.add(Alert(type=f"AI_{anomaly}", details=ai_text))
            session.commit()
            logger.info("AI alert created for %s", anomaly)
        except Exception as exc:
            logger.exception("Ollama call failed")
            session.add(Alert(type="AI_error", details=str(exc)))
            session.commit()


def check_ollama_health() -> bool:
    try:
        base = settings.ollama_url.rsplit("/api/", 1)[0]
        response = requests.get(f"{base}/api/tags", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False
