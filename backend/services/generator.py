import logging
import random
import uuid

from database import SessionLocal
from models import Alert, CDR
from services.anomalies import ANOMALIES

logger = logging.getLogger(__name__)

CARRIER_IPS = ["198.51.100.12", "203.0.113.45", "192.0.2.88", "198.18.0.50"]
INTL_PREFIXES = ["+447", "+491", "+331", "+813", "+861", "+234"]


def _phone10() -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(10))


def _random_ip() -> str:
    return f"{random.randint(11, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"


def _livetel_uri() -> str:
    return f"{_phone10()}@livetel.net"


def _external_uri() -> str:
    return f"{_phone10()}@{_random_ip()}"


def _trunk_uri() -> str:
    return f"+1{_phone10()}@{random.choice(CARRIER_IPS)}"


def _fraud_uri() -> str:
    return f"+{_phone10()}@premium-route.xyz"


def _baseline_qos() -> dict[str, float]:
    return {
        "mos": round(random.uniform(3.6, 4.5), 2),
        "latency": float(random.randint(25, 90)),
        "jitter": float(random.randint(1, 12)),
        "packet_loss": round(random.uniform(0, 1.5), 2),
    }


def _build_endpoints(direction: str, anomaly: str | None) -> tuple[str, str, str]:
    livetel = _livetel_uri()
    if direction == "inbound":
        external = _external_uri()
        return direction, external, livetel
    if anomaly == "toll_fraud":
        return direction, livetel, _fraud_uri()
    if anomaly == "suspicious_international":
        return direction, livetel, f"{random.choice(INTL_PREFIXES)}{random.randint(1000000, 9999999)}@{random.choice(CARRIER_IPS)}"
    return direction, livetel, _trunk_uri()


def _sip_flow(
    call_id: str,
    direction: str,
    from_uri: str,
    to_uri: str,
    qos: dict[str, float],
    *,
    failed: bool = False,
    with_transfer: bool = False,
    with_voicemail: bool = False,
) -> list[CDR]:
    rows: list[CDR] = []
    leg = 1

    def row(method: str, code: int, dur: int = 0, q: dict | None = None) -> CDR:
        qq = q or qos
        return CDR(
            call_id=call_id,
            direction=direction,
            sip_method=method,
            from_uri=from_uri,
            to_uri=to_uri,
            duration=dur,
            mos=qq["mos"],
            latency=qq["latency"],
            jitter=qq["jitter"],
            packet_loss=qq["packet_loss"],
            sip_code=code,
            leg=leg,
        )

    rows.append(row("INVITE", 100))
    rows.append(row("INVITE", 180))
    if failed:
        rows.append(row("INVITE", random.choice([503, 408, 403, 401])))
        return rows

    dur = random.randint(15, 480)
    rows.append(row("INVITE", 200, dur))

    if with_voicemail and random.random() < 0.5:
        rows.append(row("REFER", 202))
        vm = f"voicemail@{_random_ip()}"
        rows.append(
            CDR(
                call_id=call_id,
                direction=direction,
                sip_method="INVITE",
                from_uri=from_uri,
                to_uri=vm,
                duration=random.randint(5, 30),
                mos=3.8,
                latency=qos["latency"],
                jitter=qos["jitter"],
                packet_loss=qos["packet_loss"],
                sip_code=200,
                leg=2,
            )
        )

    if with_transfer and random.random() < 0.4:
        rows.append(row("REFER", 202))
        xfer_to = _livetel_uri() if direction == "inbound" else _trunk_uri()
        rows.append(
            CDR(
                call_id=call_id,
                direction=direction,
                sip_method="INVITE",
                from_uri=from_uri,
                to_uri=xfer_to,
                duration=random.randint(30, 300),
                mos=qos["mos"],
                latency=qos["latency"],
                jitter=qos["jitter"],
                packet_loss=qos["packet_loss"],
                sip_code=200,
                leg=2,
            )
        )

    rows.append(row("BYE", 200))
    return rows


def _apply_qos_anomaly(qos: dict[str, float], anomaly: str) -> dict[str, float]:
    q = dict(qos)
    if anomaly == "congestion":
        q.update(latency=float(random.randint(250, 500)), jitter=float(random.randint(35, 90)), packet_loss=round(random.uniform(6, 18), 2), mos=round(random.uniform(1.4, 2.4), 2))
    elif anomaly == "latency_spike":
        q.update(latency=float(random.randint(180, 350)), mos=round(random.uniform(2.5, 3.2), 2))
    elif anomaly == "mos_degradation":
        q.update(mos=round(random.uniform(1.2, 2.5), 2), packet_loss=round(random.uniform(2, 6), 2))
    elif anomaly == "one_way_audio":
        q.update(packet_loss=round(random.uniform(8, 22), 2), jitter=float(random.randint(20, 50)))
    return q


def generate_call_session(anomaly: str | None = None) -> list[CDR]:
    call_id = uuid.uuid4().hex[:16]
    direction = random.choice(["inbound", "outbound"])
    direction, from_uri, to_uri = _build_endpoints(direction, anomaly)
    qos = _baseline_qos()
    if anomaly:
        qos = _apply_qos_anomaly(qos, anomaly)

    failed = anomaly in ("carrier_outage", "trunk_exhaustion", "auth_failure", "dns_sip_failure")
    if anomaly == "auth_failure":
        qos = _baseline_qos()

    return _sip_flow(
        call_id,
        direction,
        from_uri,
        to_uri,
        qos,
        failed=failed,
        with_transfer=anomaly is None and random.random() < 0.12,
        with_voicemail=anomaly is None and random.random() < 0.08,
    )


def baseline_traffic() -> None:
    with SessionLocal() as session:
        for _ in range(random.randint(2, 5)):
            for cdr in generate_call_session():
                session.add(cdr)
        session.commit()


def inject_anomaly() -> None:
    anomaly_key = random.choice(list(ANOMALIES.keys()))
    meta = ANOMALIES[anomaly_key]
    with SessionLocal() as session:
        for _ in range(random.randint(8, 15)):
            for cdr in generate_call_session(anomaly=anomaly_key):
                session.add(cdr)
        session.add(
            Alert(
                type=anomaly_key,
                severity=meta.severity,
                details=f"Injected {meta.label} burst — correlated SIP events in telemetry window.",
            )
        )
        session.commit()
    logger.info("Injected %s (%s) anomaly burst", anomaly_key, meta.severity)
