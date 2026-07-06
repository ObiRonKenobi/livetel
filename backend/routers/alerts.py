from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, not_, or_
from sqlalchemy.orm import Session

from database import get_db
from models import Alert, CDR
from routers.cdrs import _cdr_to_response
from schemas import AlertContextResponse, AlertResponse, AlertStatsResponse, DismissAlertRequest
from services.anomalies import ANOMALIES, LEGACY_KEY_MAP
from services.template_analysis import template_mitigation, template_root_cause

router = APIRouter(prefix="/api", tags=["alerts"])

VALID_DISMISS = frozenset({"false_positive", "resolved"})
ALERT_WINDOW_HOURS = 24


def _alert_cutoff() -> datetime:
    return datetime.utcnow() - timedelta(hours=ALERT_WINDOW_HOURS)


def _hide_legacy_ai():
    """Exclude deprecated AI-prefixed alerts from the dashboard."""
    return not_(or_(Alert.type.like("AI_%"), Alert.type == "AI_error"))


def _normalize_type(alert_type: str) -> str:
    base = alert_type.removeprefix("AI_")
    return LEGACY_KEY_MAP.get(base, base)


def _parse_details(details: str) -> tuple[str, str]:
    root = ""
    mit = ""
    if "Root cause:" in details:
        after = details.split("Root cause:", 1)[1]
        if "Immediate mitigation:" in after:
            root, mit = after.split("Immediate mitigation:", 1)
        else:
            root = after
    return root.strip(), mit.strip()


@router.get("/alerts/stats", response_model=AlertStatsResponse)
def get_alert_stats(db: Session = Depends(get_db)) -> AlertStatsResponse:
    cutoff = _alert_cutoff()
    open_count, false_positive, resolved = (
        db.query(
            func.sum(case((Alert.dismissed_status.is_(None), 1), else_=0)),
            func.sum(case((Alert.dismissed_status == "false_positive", 1), else_=0)),
            func.sum(case((Alert.dismissed_status == "resolved", 1), else_=0)),
        )
        .filter(Alert.timestamp >= cutoff, _hide_legacy_ai())
        .one()
    )
    return AlertStatsResponse(
        open=int(open_count or 0),
        false_positive=int(false_positive or 0),
        resolved=int(resolved or 0),
        window_hours=ALERT_WINDOW_HOURS,
    )


@router.get("/alerts", response_model=list[AlertResponse])
def get_alerts(db: Session = Depends(get_db)) -> list[AlertResponse]:
    alerts = (
        db.query(Alert)
        .filter(
            Alert.timestamp >= _alert_cutoff(),
            Alert.dismissed_status.is_(None),
            _hide_legacy_ai(),
        )
        .order_by(Alert.timestamp.desc())
        .limit(100)
        .all()
    )
    return [
        AlertResponse(
            id=a.id,
            time=a.timestamp.isoformat() + "Z",
            type=a.type,
            severity=a.severity,
            details=a.details,
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/dismiss")
def dismiss_alert(
    alert_id: int,
    body: DismissAlertRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if body.status not in VALID_DISMISS:
        raise HTTPException(status_code=400, detail="status must be false_positive or resolved")
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.dismissed_status = body.status
    db.commit()
    return {"ok": "true", "status": body.status}


@router.get("/alerts/{alert_id}/context", response_model=AlertContextResponse)
def get_alert_context(alert_id: int, db: Session = Depends(get_db)) -> AlertContextResponse:
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    base_type = _normalize_type(alert.type)
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
        time=alert.timestamp.isoformat() + "Z",
        type=alert.type,
        severity=alert.severity,
        details=alert.details,
    )

    root, mit = _parse_details(alert.details)
    if not root:
        meta = ANOMALIES.get(base_type)
        label = meta.label if meta else base_type.replace("_", " ").title()
        root = template_root_cause(base_type, label)
    if not mit:
        mit = template_mitigation(base_type)

    return AlertContextResponse(
        alert=alert_resp,
        related_events=[_cdr_to_response(r) for r in related],
        root_cause=root,
        mitigation=mit,
    )
