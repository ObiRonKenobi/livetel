import logging
import random

from database import SessionLocal
from models import Alert, CDR

logger = logging.getLogger(__name__)

DESTINATIONS = ["US", "US", "UK", "DE", "FR", "JP", "IN", "BR", "NG", "RU"]
ANOMALY_TYPES = ("toll_fraud", "carrier_outage", "congestion")


def _generate_cdr() -> CDR:
    dst = f"{random.choice(DESTINATIONS)}_{random.randint(100000, 999999)}"
    return CDR(
        src=f"user_{random.randint(1000, 9999)}",
        dst=dst,
        duration=random.randint(10, 600),
        mos=round(random.uniform(3.5, 4.5), 1),
        latency=float(random.randint(30, 100)),
        jitter=float(random.randint(1, 15)),
        packet_loss=round(random.uniform(0, 2), 2),
        sip_code=random.choice([200, 200, 200, 200, 503, 408]),
    )


def _apply_anomaly(cdr: CDR, anomaly_type: str) -> None:
    if anomaly_type == "toll_fraud":
        cdr.dst = f"XYZ_{random.randint(100000, 999999)}"
        cdr.duration = random.randint(600, 3600)
    elif anomaly_type == "carrier_outage":
        cdr.sip_code = random.choice([503, 408])
        cdr.mos = round(random.uniform(1.0, 2.0), 1)
    elif anomaly_type == "congestion":
        cdr.latency = float(random.randint(250, 500))
        cdr.jitter = float(random.randint(30, 80))
        cdr.packet_loss = round(random.uniform(5, 15), 2)
        cdr.mos = round(random.uniform(1.5, 2.5), 1)


def baseline_traffic() -> None:
    with SessionLocal() as session:
        for _ in range(random.randint(3, 8)):
            session.add(_generate_cdr())
        session.commit()


def inject_anomaly() -> None:
    anomaly_type = random.choice(ANOMALY_TYPES)
    with SessionLocal() as session:
        for _ in range(30):
            cdr = _generate_cdr()
            _apply_anomaly(cdr, anomaly_type)
            session.add(cdr)
        session.add(Alert(type=anomaly_type, details="Injected anomaly burst"))
        session.commit()
    logger.info("Injected %s anomaly burst (30 CDRs)", anomaly_type)
