from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Alert, CDR
from routers.cdrs import _cdr_to_response
from schemas import AlertContextResponse, AlertResponse
from services.anomalies import ANOMALIES
from services.template_analysis import template_mitigation, template_root_cause

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=list[AlertResponse])
def get_alerts(db: Session = Depends(get_db)) -> list[AlertResponse]:
    cutoff = datetime.utcnow() - timedelta(hours=settings.prune_hours)
    alerts = (
        db.query(Alert)
        .filter(Alert.timestamp >= cutoff)
        .order_by(Alert.timestamp.desc())
        .limit(100)
        .all()
    )
    return [
        AlertResponse(
            id=a.id,
            time=a.timestamp.isoformat(),
            type=a.type,
            severity=a.severity,
            details=a.details,
        )
        for a in alerts
    ]


@router.get("/alerts/{alert_id}/context", response_model=AlertContextResponse)
def get_alert_context(alert_id: int, db: Session = Depends(get_db)) -> AlertContextResponse:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    base_type = alert.type.removeprefix("AI_")
    window_start = alert.timestamp - timedelta(seconds=90)
    window_end = alert.timestamp + timedelta(seconds=30)

    related = (
        db.query(CDR)
        .filter(CDR.timestamp >= window_start, CDR.timestamp <= window_end)
        .order_by(CDR.timestamp.desc())
        .limit(80)
        .all()
    )

    alert_resp = AlertResponse(
        id=alert.id,
        time=alert.timestamp.isoformat(),
        type=alert.type,
        severity=alert.severity,
        details=alert.details,
    )

    if alert.type.startswith("AI_"):
        return AlertContextResponse(
            alert=alert_resp,
            related_events=[_cdr_to_response(r) for r in related],
            root_cause=alert.details.split("\n\n")[1] if "\n\n" in alert.details else alert.details,
            mitigation=alert.details.split("Immediate mitigation:")[-1] if "mitigation" in alert.details.lower() else "",
        )

    meta = ANOMALIES.get(base_type)
    label = meta.label if meta else base_type
    return AlertContextResponse(
        alert=alert_resp,
        related_events=[_cdr_to_response(r) for r in related],
        root_cause=template_root_cause(base_type, label),
        mitigation=template_mitigation(base_type),
    )
