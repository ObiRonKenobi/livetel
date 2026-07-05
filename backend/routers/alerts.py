from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import Alert
from schemas import AlertResponse

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=list[AlertResponse])
def get_alerts(db: Session = Depends(get_db)) -> list[AlertResponse]:
    cutoff = datetime.utcnow() - timedelta(hours=settings.prune_hours)
    alerts = (
        db.query(Alert)
        .filter(Alert.timestamp >= cutoff)
        .order_by(Alert.timestamp.desc())
        .limit(50)
        .all()
    )
    return [
        AlertResponse(time=a.timestamp.isoformat(), type=a.type, details=a.details)
        for a in alerts
    ]
