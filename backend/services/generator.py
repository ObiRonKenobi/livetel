"""SIP CDR generator with live concurrent call simulation."""

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from database import SessionLocal
from models import Alert, CDR
from services.anomalies import ANOMALIES

logger = logging.getLogger(__name__)

CARRIER_IPS = ["198.51.100.12", "203.0.113.45", "192.0.2.88", "198.18.0.50"]
INTL_PREFIXES = ["+447", "+491", "+331", "+813", "+861", "+234"]

TARGET_ACTIVE_MIN = 100
TARGET_ACTIVE_MAX = 150


@dataclass
class LiveCall:
    call_id: str
    direction: str
    from_uri: str
    to_uri: str
    qos: dict[str, float]
    duration_sec: int
    started_at: datetime
    answered_at: datetime
    end_at: datetime
    anomaly: str | None = None
    with_transfer: bool = False
    with_voicemail: bool = False
    transfer_done: bool = False
    voicemail_done: bool = False
    failed: bool = False


_live: dict[str, LiveCall] = {}
_seeded = False


def active_call_count() -> int:
    """Calls that have been answered (200 OK) and not yet hung up (BYE)."""
    return len(_live)


def avg_call_duration_sec() -> float:
    """Mean planned duration (seconds) for currently live calls."""
    if not _live:
        return 0.0
    return sum(c.duration_sec for c in _live.values()) / len(_live)


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
        return (
            direction,
            livetel,
            f"{random.choice(INTL_PREFIXES)}{random.randint(1000000, 9999999)}@{random.choice(CARRIER_IPS)}",
        )
    return direction, livetel, _trunk_uri()


def _apply_qos_anomaly(qos: dict[str, float], anomaly: str) -> dict[str, float]:
    q = dict(qos)
    if anomaly == "congestion":
        q.update(
            latency=float(random.randint(250, 500)),
            jitter=float(random.randint(35, 90)),
            packet_loss=round(random.uniform(6, 18), 2),
            mos=round(random.uniform(1.4, 2.4), 2),
        )
    elif anomaly == "latency_spike":
        q.update(latency=float(random.randint(180, 350)), mos=round(random.uniform(2.5, 3.2), 2))
    elif anomaly == "mos_degradation":
        q.update(mos=round(random.uniform(1.2, 2.5), 2), packet_loss=round(random.uniform(2, 6), 2))
    elif anomaly == "one_way_audio":
        q.update(packet_loss=round(random.uniform(8, 22), 2), jitter=float(random.randint(20, 50)))
    return q


def _cdr(
    lc: LiveCall,
    *,
    method: str,
    code: int,
    ts: datetime,
    dur: int = 0,
    leg: int = 1,
    from_uri: str | None = None,
    to_uri: str | None = None,
    qos: dict[str, float] | None = None,
) -> CDR:
    qq = qos or lc.qos
    return CDR(
        timestamp=ts,
        call_id=lc.call_id,
        direction=lc.direction,
        sip_method=method,
        from_uri=from_uri or lc.from_uri,
        to_uri=to_uri or lc.to_uri,
        duration=dur,
        mos=qq["mos"],
        latency=qq["latency"],
        jitter=qq["jitter"],
        packet_loss=qq["packet_loss"],
        sip_code=code,
        leg=leg,
    )


def _new_live_call(anomaly: str | None, *, now: datetime | None = None) -> LiveCall:
    now = now or datetime.utcnow()
    call_id = uuid.uuid4().hex[:16]
    direction = random.choice(["inbound", "outbound"])
    direction, from_uri, to_uri = _build_endpoints(direction, anomaly)
    qos = _baseline_qos()
    if anomaly:
        qos = _apply_qos_anomaly(qos, anomaly)

    failed = anomaly in ("carrier_outage", "trunk_exhaustion", "auth_failure", "dns_sip_failure")
    if anomaly == "auth_failure":
        qos = _baseline_qos()

    duration_sec = random.randint(60, 360) if not failed else random.randint(5, 20)
    ring_sec = random.randint(2, 8)
    answered_at = now + timedelta(seconds=ring_sec)
    end_at = answered_at + timedelta(seconds=duration_sec)

    return LiveCall(
        call_id=call_id,
        direction=direction,
        from_uri=from_uri,
        to_uri=to_uri,
        qos=qos,
        duration_sec=duration_sec,
        started_at=now,
        answered_at=answered_at,
        end_at=end_at,
        anomaly=anomaly,
        with_transfer=anomaly is None and random.random() < 0.12,
        with_voicemail=anomaly is None and random.random() < 0.08,
        failed=failed,
    )


def _setup_cdrs(lc: LiveCall, ts: datetime) -> list[CDR]:
    rows = [
        _cdr(lc, method="INVITE", code=100, ts=ts - timedelta(milliseconds=200)),
        _cdr(lc, method="INVITE", code=180, ts=ts - timedelta(milliseconds=100)),
    ]
    if lc.failed:
        fail_code = random.choice([503, 408, 403, 401])
        rows.append(_cdr(lc, method="INVITE", code=fail_code, ts=ts))
        return rows
    rows.append(_cdr(lc, method="INVITE", code=200, ts=ts, dur=lc.duration_sec))
    return rows


def _transfer_cdrs(lc: LiveCall, ts: datetime) -> list[CDR]:
    xfer_to = _livetel_uri() if lc.direction == "inbound" else _trunk_uri()
    return [
        _cdr(lc, method="REFER", code=202, ts=ts),
        _cdr(
            lc,
            method="INVITE",
            code=200,
            ts=ts + timedelta(milliseconds=50),
            dur=random.randint(30, 180),
            leg=2,
            to_uri=xfer_to,
        ),
    ]


def _voicemail_cdrs(lc: LiveCall, ts: datetime) -> list[CDR]:
    vm = f"voicemail@{_random_ip()}"
    return [
        _cdr(lc, method="REFER", code=202, ts=ts),
        _cdr(
            lc,
            method="INVITE",
            code=200,
            ts=ts + timedelta(milliseconds=50),
            dur=random.randint(5, 30),
            leg=2,
            to_uri=vm,
            qos={**lc.qos, "mos": 3.8},
        ),
    ]


def _teardown_cdrs(lc: LiveCall, ts: datetime) -> list[CDR]:
    if lc.failed:
        return []
    return [_cdr(lc, method="BYE", code=200, ts=ts)]


def _seed_live_calls() -> None:
    global _seeded
    if _seeded:
        return
    _seeded = True
    now = datetime.utcnow()
    target = random.randint(110, 130)
    with SessionLocal() as session:
        for _ in range(target):
            lc = _new_live_call(None, now=now)
            remaining = random.randint(20, lc.duration_sec)
            lc.end_at = now + timedelta(seconds=remaining)
            lc.started_at = now - timedelta(seconds=lc.duration_sec - remaining + random.randint(2, 8))
            lc.answered_at = lc.started_at + timedelta(seconds=random.randint(2, 8))
            for row in _setup_cdrs(lc, lc.answered_at):
                session.add(row)
            _live[lc.call_id] = lc
        session.commit()
    logger.info("Seeded %d live concurrent calls", len(_live))


def tick_live_calls() -> None:
    """Advance live calls: emit SIP events, hang up completed calls, start new ones."""
    _seed_live_calls()
    now = datetime.utcnow()

    with SessionLocal() as session:
        for call_id, lc in list(_live.items()):
            if lc.failed:
                if now >= lc.end_at:
                    del _live[call_id]
                continue

            elapsed = (now - lc.answered_at).total_seconds()
            if lc.with_transfer and not lc.transfer_done and elapsed >= lc.duration_sec * 0.35:
                lc.transfer_done = True
                for row in _transfer_cdrs(lc, now):
                    session.add(row)
            if lc.with_voicemail and not lc.voicemail_done and elapsed >= lc.duration_sec * 0.55:
                lc.voicemail_done = True
                for row in _voicemail_cdrs(lc, now):
                    session.add(row)

            if now >= lc.end_at:
                for row in _teardown_cdrs(lc, now):
                    session.add(row)
                del _live[call_id]

        target = random.randint(TARGET_ACTIVE_MIN, TARGET_ACTIVE_MAX)
        deficit = target - len(_live)
        if deficit > 0:
            n_start = min(deficit, random.randint(1, 3))
            for _ in range(n_start):
                lc = _new_live_call(None, now=now)
                for row in _setup_cdrs(lc, now):
                    session.add(row)
                if lc.failed:
                    lc.end_at = now + timedelta(seconds=random.randint(3, 15))
                _live[lc.call_id] = lc

        session.commit()


def baseline_traffic() -> None:
    tick_live_calls()


def generate_call_session(anomaly: str | None = None) -> list[CDR]:
    """Instant complete session for anomaly bursts (does not affect live call count)."""
    now = datetime.utcnow()
    lc = _new_live_call(anomaly, now=now)
    rows = _setup_cdrs(lc, now)
    if not lc.failed:
        if lc.with_transfer:
            rows.extend(_transfer_cdrs(lc, now + timedelta(seconds=1)))
        if lc.with_voicemail:
            rows.extend(_voicemail_cdrs(lc, now + timedelta(seconds=2)))
        rows.extend(_teardown_cdrs(lc, now + timedelta(seconds=3)))
    return rows


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
