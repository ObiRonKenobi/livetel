import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import Alert, CDR

logger = logging.getLogger(__name__)


def prune_old_data() -> None:
    cutoff = datetime.utcnow() - timedelta(hours=settings.prune_hours)
    with SessionLocal() as session:
        cdr_deleted = session.query(CDR).filter(CDR.timestamp < cutoff).delete()
        alert_deleted = session.query(Alert).filter(Alert.timestamp < cutoff).delete()
        session.commit()
        if cdr_deleted or alert_deleted:
            logger.info("Pruned %d CDRs and %d alerts older than %dh", cdr_deleted, alert_deleted, settings.prune_hours)
