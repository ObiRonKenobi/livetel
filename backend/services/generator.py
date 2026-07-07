"""SIP CDR generator with live concurrent B2BUA (two-leg) call simulation."""

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from database import SessionLocal
from models import Alert, CDR
from services.anomalies import ANOMALIES

logger = logging.getLogger(__name__)

CARRIER_IPS = ["198.51.100.12", "203.0.113.45", "192.0.2.88", "198.18.0.50"]
INTL_PREFIXES = ["+447", "+491", "+331", "+813", "+861", "+234"]
SBC_URI = "sbc@livetel.net"

TARGET_ACTIVE_MIN = 100
TARGET_ACTIVE_MAX = 150
RING_SEC_MIN = 8
RING_SEC_MAX = 25
TALK_SEC_MIN = 120
TALK_SEC_MAX = 720
TRUNK_AUTH_CHANCE = 0.18

# Failures on egress (carrier/trunk) — leg 1 may ring, leg 2 rejects.
_EGRESS_FAIL_ANOMALIES = frozenset({
    "sip_trunk_unreachable",
    "sip_503_overload",
    "sip_dns_timeout",
})

# Failures on ingress — leg 2 never attempted.
_INGRESS_FAIL_ANOMALIES = frozenset({
    "auth_failure",
    "softphone_registration_failure",
})

_FAIL_ANOMALIES = _EGRESS_FAIL_ANOMALIES | _INGRESS_FAIL_ANOMALIES

_EGRESS_FAIL_CODES: dict[str, list[int]] = {
    "sip_503_overload": [503],
    "sip_trunk_unreachable": [503, 503, 408],
    "sip_dns_timeout": [408],
}

_INGRESS_FAIL_CODES: dict[str, list[int]] = {
    "auth_failure": [401, 403],
    "softphone_registration_failure": [401, 403],
}

_QOS_ANOMALIES = frozenset({
    "rtp_packet_loss",
    "sip_latency_spike",
    "codec_quality_drop",
    "one_way_audio",
    "congestion",
    "latency_spike",
    "mos_degradation",
})


@dataclass
class LiveCall:
    call_id: str
    direction: str  # inbound | outbound (tenant perspective)
    caller_uri: str  # leg 1 From
    livetel_uri: str  # leg 1 To (inbound) or leg 1 From (outbound)
    trunk_uri: str  # leg 2 To (carrier / PSTN)
    qos: dict[str, float]
    qos_leg2: dict[str, float] = field(default_factory=dict)
    ring_sec: int = 12
    duration_sec: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    answered_at: datetime = field(default_factory=datetime.utcnow)
    end_at: datetime = field(default_factory=datetime.utcnow)
    anomaly: str | None = None
    with_transfer: bool = False
    with_voicemail: bool = False
    transfer_done: bool = False
    voicemail_done: bool = False
    failed: bool = False
    fail_leg: int | None = None
    fail_code: int | None = None
    ring_before_fail: bool = False
    trunk_auth: bool = False


_live: dict[str, LiveCall] = {}
_pending: dict[str, LiveCall] = {}  # ringing; answer CDRs emitted when answered_at reached
_seeded = False


def active_call_count() -> int:
    return len(_live)


def active_call_ids() -> set[str]:
    return set(_live.keys())


def avg_call_duration_sec() -> float:
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


def _apply_qos_anomaly(qos: dict[str, float], anomaly: str) -> dict[str, float]:
    q = dict(qos)
    if anomaly in ("congestion", "rtp_packet_loss"):
        q.update(
            latency=float(random.randint(250, 500)),
            jitter=float(random.randint(35, 90)),
            packet_loss=round(random.uniform(6, 18), 2),
            mos=round(random.uniform(1.4, 2.4), 2),
        )
    elif anomaly in ("latency_spike", "sip_latency_spike"):
        q.update(latency=float(random.randint(180, 350)), mos=round(random.uniform(2.5, 3.2), 2))
    elif anomaly in ("mos_degradation", "codec_quality_drop"):
        q.update(mos=round(random.uniform(1.2, 2.5), 2), packet_loss=round(random.uniform(2, 6), 2))
    elif anomaly == "one_way_audio":
        q.update(packet_loss=round(random.uniform(8, 22), 2), jitter=float(random.randint(20, 50)))
    return q


def _build_uris(direction: str, anomaly: str | None) -> tuple[str, str, str]:
    """caller_uri, livetel_uri, trunk_uri for the B2BUA session."""
    livetel = _livetel_uri()
    if direction == "inbound":
        return _external_uri(), livetel, _trunk_uri()
    if anomaly == "toll_fraud":
        return livetel, livetel, _fraud_uri()
    if anomaly == "suspicious_international":
        intl = f"{random.choice(INTL_PREFIXES)}{random.randint(1000000, 9999999)}@{random.choice(CARRIER_IPS)}"
        return livetel, livetel, intl
    dest = _trunk_uri()
    return livetel, livetel, dest


def _failure_plan(anomaly: str | None) -> tuple[bool, int | None, int | None, int | None, bool]:
    """failed, fail_leg, fail_code, ring_before_fail."""
    if not anomaly or anomaly not in _FAIL_ANOMALIES:
        return False, None, None, None, False
    if anomaly in _INGRESS_FAIL_ANOMALIES:
        code = random.choice(_INGRESS_FAIL_CODES[anomaly])
        return True, 1, code, None, False
    code = random.choice(_EGRESS_FAIL_CODES.get(anomaly, [503]))
    ring = anomaly in ("sip_503_overload", "sip_trunk_unreachable") and random.random() < 0.65
    return True, 2, code, None, ring


def _new_live_call(anomaly: str | None, *, now: datetime | None = None) -> LiveCall:
    now = now or datetime.utcnow()
    direction = random.choice(["inbound", "outbound"])
    caller_uri, livetel_uri, trunk_uri = _build_uris(direction, anomaly)
    qos = _baseline_qos()
    qos_leg2 = dict(qos)
    if anomaly and anomaly in _QOS_ANOMALIES:
        qos_leg2 = _apply_qos_anomaly(qos, anomaly)

    failed, fail_leg, fail_code, _, ring_before_fail = _failure_plan(anomaly)
    if anomaly == "auth_failure":
        qos = _baseline_qos()
        qos_leg2 = dict(qos)

    duration_sec = random.randint(TALK_SEC_MIN, TALK_SEC_MAX) if not failed else 0
    ring_sec = random.randint(RING_SEC_MIN, RING_SEC_MAX) if not failed else random.randint(4, 12)
    started_at = now
    answered_at = now + timedelta(seconds=ring_sec) if not failed else now
    end_at = answered_at + timedelta(seconds=duration_sec) if not failed else now
    trunk_auth = not failed and random.random() < TRUNK_AUTH_CHANCE

    return LiveCall(
        call_id=uuid.uuid4().hex[:16],
        direction=direction,
        caller_uri=caller_uri,
        livetel_uri=livetel_uri,
        trunk_uri=trunk_uri,
        qos=qos,
        qos_leg2=qos_leg2,
        ring_sec=ring_sec,
        duration_sec=duration_sec,
        started_at=started_at,
        answered_at=answered_at,
        end_at=end_at,
        anomaly=anomaly,
        with_transfer=anomaly is None and random.random() < 0.12,
        with_voicemail=anomaly is None and random.random() < 0.08,
        failed=failed,
        fail_leg=fail_leg,
        fail_code=fail_code,
        ring_before_fail=ring_before_fail,
        trunk_auth=trunk_auth,
    )


def _leg1_endpoints(lc: LiveCall) -> tuple[str, str, str]:
    if lc.direction == "inbound":
        return "inbound", lc.caller_uri, lc.livetel_uri
    return "outbound", lc.livetel_uri, lc.trunk_uri


def _leg2_endpoints(lc: LiveCall) -> tuple[str, str, str]:
    return "outbound", SBC_URI, lc.trunk_uri


def _row(
    lc: LiveCall,
    *,
    leg: int,
    method: str,
    code: int,
    ts: datetime,
    dur: int = 0,
    from_uri: str | None = None,
    to_uri: str | None = None,
    qos: dict[str, float] | None = None,
) -> CDR:
    if leg == 1:
        direction, default_from, default_to = _leg1_endpoints(lc)
    else:
        direction, default_from, default_to = _leg2_endpoints(lc)
    qq = qos or (lc.qos_leg2 if leg == 2 else lc.qos)
    return CDR(
        timestamp=ts,
        call_id=lc.call_id,
        direction=direction,
        sip_method=method,
        from_uri=from_uri or default_from,
        to_uri=to_uri or default_to,
        duration=dur,
        mos=qq["mos"],
        latency=qq["latency"],
        jitter=qq["jitter"],
        packet_loss=qq["packet_loss"],
        sip_code=code,
        leg=leg,
    )


def _ingress_auth_failure(lc: LiveCall) -> list[CDR]:
    code = lc.fail_code or 401
    t0 = lc.started_at
    rows = [
        _row(lc, leg=1, method="INVITE", code=0, ts=t0),
        _row(lc, leg=1, method="INVITE", code=100, ts=t0 + timedelta(milliseconds=90)),
    ]
    if lc.anomaly == "softphone_registration_failure" and random.random() < 0.5:
        rows.extend([
            _row(lc, leg=1, method="REGISTER", code=0, ts=t0 + timedelta(milliseconds=40)),
            _row(lc, leg=1, method="REGISTER", code=100, ts=t0 + timedelta(milliseconds=120)),
            _row(lc, leg=1, method="REGISTER", code=code, ts=t0 + timedelta(milliseconds=280)),
        ])
    rows.append(_row(lc, leg=1, method="INVITE", code=code, ts=t0 + timedelta(milliseconds=450)))
    return rows


def _egress_failure(lc: LiveCall) -> list[CDR]:
    code = lc.fail_code or 503
    start = lc.started_at
    fail_at = start + timedelta(seconds=lc.ring_sec if lc.ring_before_fail else random.uniform(0.8, 2.5))
    rows = [
        _row(lc, leg=1, method="INVITE", code=0, ts=start),
        _row(lc, leg=2, method="INVITE", code=0, ts=start + timedelta(milliseconds=random.randint(50, 160))),
        _row(lc, leg=1, method="INVITE", code=100, ts=start + timedelta(milliseconds=random.randint(70, 200))),
        _row(lc, leg=2, method="INVITE", code=100, ts=start + timedelta(milliseconds=random.randint(100, 260))),
    ]
    if lc.ring_before_fail:
        ring_at = start + timedelta(seconds=random.uniform(1.2, 3.0))
        rows.extend([
            _row(lc, leg=1, method="INVITE", code=180, ts=ring_at),
            _row(lc, leg=2, method="INVITE", code=180, ts=ring_at + timedelta(milliseconds=random.randint(30, 90))),
        ])
    rows.extend([
        _row(lc, leg=2, method="INVITE", code=code, ts=fail_at - timedelta(milliseconds=random.randint(40, 120))),
        _row(lc, leg=1, method="INVITE", code=code, ts=fail_at),
    ])
    if lc.ring_before_fail and random.random() < 0.4:
        rows.append(_row(lc, leg=1, method="CANCEL", code=487, ts=fail_at + timedelta(milliseconds=random.randint(60, 200))))
    return rows


def _leg2_trunk_auth(lc: LiveCall, start: datetime) -> list[CDR]:
    """407 Proxy-Authenticate on egress, then ACK with credentials."""
    t407 = start + timedelta(milliseconds=random.randint(180, 420))
    tack = t407 + timedelta(milliseconds=random.randint(30, 90))
    return [
        _row(lc, leg=2, method="INVITE", code=407, ts=t407),
        _row(lc, leg=2, method="ACK", code=0, ts=tack),
    ]


def _setup_early_cdrs(lc: LiveCall) -> list[CDR]:
    """Through 180 Ringing — emitted when the call is offered."""
    if lc.failed:
        return _setup_cdrs(lc)
    start = lc.started_at
    ring_early = start + timedelta(seconds=random.uniform(1.0, 3.5))
    t_inv_l2 = start + timedelta(milliseconds=random.randint(45, 180))
    t_try_l1 = start + timedelta(milliseconds=random.randint(70, 220))
    t_try_l2 = t_inv_l2 + timedelta(milliseconds=random.randint(50, 180))
    rows = [
        _row(lc, leg=1, method="INVITE", code=0, ts=start),
        _row(lc, leg=2, method="INVITE", code=0, ts=t_inv_l2),
        _row(lc, leg=1, method="INVITE", code=100, ts=t_try_l1),
        _row(lc, leg=2, method="INVITE", code=100, ts=t_try_l2),
    ]
    if lc.trunk_auth:
        rows.extend(_leg2_trunk_auth(lc, start))
        rows.append(_row(lc, leg=2, method="INVITE", code=100, ts=t_try_l2 + timedelta(milliseconds=random.randint(120, 280))))
    rows.extend([
        _row(lc, leg=1, method="INVITE", code=180, ts=ring_early),
        _row(lc, leg=2, method="INVITE", code=180, ts=ring_early + timedelta(milliseconds=random.randint(25, 100))),
    ])
    return rows


def _answer_cdrs(lc: LiveCall) -> list[CDR]:
    """200 OK + ACK when callee answers."""
    answer = lc.answered_at
    return [
        _row(lc, leg=1, method="INVITE", code=200, ts=answer, dur=lc.duration_sec),
        _row(lc, leg=2, method="INVITE", code=200, ts=answer + timedelta(milliseconds=random.randint(30, 120)), dur=lc.duration_sec),
        _row(lc, leg=1, method="ACK", code=0, ts=answer + timedelta(milliseconds=random.randint(40, 150))),
        _row(lc, leg=2, method="ACK", code=0, ts=answer + timedelta(milliseconds=random.randint(80, 200))),
    ]


def _successful_setup(lc: LiveCall) -> list[CDR]:
    return _setup_early_cdrs(lc) + _answer_cdrs(lc)


def _setup_cdrs(lc: LiveCall) -> list[CDR]:
    if lc.failed and lc.fail_leg == 1:
        return _ingress_auth_failure(lc)
    if lc.failed and lc.fail_leg == 2:
        return _egress_failure(lc)
    return _successful_setup(lc)


def _transfer_cdrs(lc: LiveCall, ts: datetime) -> list[CDR]:
    xfer_to = _livetel_uri() if lc.direction == "inbound" else _trunk_uri()
    return [
        _row(lc, leg=1, method="REFER", code=202, ts=ts),
        _row(
            lc,
            leg=2,
            method="INVITE",
            code=200,
            ts=ts + timedelta(milliseconds=80),
            dur=random.randint(30, 180),
            to_uri=xfer_to,
        ),
    ]


def _voicemail_cdrs(lc: LiveCall, ts: datetime) -> list[CDR]:
    vm = f"voicemail@{_random_ip()}"
    return [
        _row(lc, leg=1, method="REFER", code=202, ts=ts),
        _row(
            lc,
            leg=2,
            method="INVITE",
            code=200,
            ts=ts + timedelta(milliseconds=80),
            dur=random.randint(5, 30),
            to_uri=vm,
            qos={**lc.qos, "mos": 3.8},
        ),
    ]


def _teardown_cdrs(lc: LiveCall, ts: datetime) -> list[CDR]:
    if lc.failed:
        return []
    return [
        _row(lc, leg=1, method="BYE", code=200, ts=ts),
        _row(lc, leg=2, method="BYE", code=200, ts=ts + timedelta(milliseconds=40)),
    ]


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
            elapsed_talk = random.randint(30, min(lc.duration_sec, TALK_SEC_MAX))
            lc.answered_at = now - timedelta(seconds=elapsed_talk)
            lc.started_at = lc.answered_at - timedelta(seconds=lc.ring_sec)
            lc.end_at = lc.answered_at + timedelta(seconds=lc.duration_sec)
            for row in _setup_cdrs(lc):
                session.add(row)
            _live[lc.call_id] = lc
        session.commit()
    logger.info("Seeded %d live concurrent calls", len(_live))


def tick_live_calls() -> None:
    _seed_live_calls()
    now = datetime.utcnow()

    with SessionLocal() as session:
        for call_id, lc in list(_pending.items()):
            if now >= lc.answered_at:
                if not lc.failed:
                    for row in _answer_cdrs(lc):
                        session.add(row)
                    _live[call_id] = lc
                del _pending[call_id]

        for call_id, lc in list(_live.items()):
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
        deficit = target - len(_live) - len(_pending)
        if deficit > 0:
            n_start = min(deficit, random.randint(1, 3))
            for _ in range(n_start):
                lc = _new_live_call(None, now=now)
                if lc.failed:
                    for row in _setup_cdrs(lc):
                        session.add(row)
                else:
                    for row in _setup_early_cdrs(lc):
                        session.add(row)
                    _pending[lc.call_id] = lc

        session.commit()


def baseline_traffic() -> None:
    tick_live_calls()


def generate_call_session(anomaly: str | None = None) -> list[CDR]:
    now = datetime.utcnow()
    lc = _new_live_call(anomaly, now=now)
    if lc.failed:
        lc.started_at = now - timedelta(seconds=lc.ring_sec if lc.ring_before_fail else random.randint(1, 3))
    else:
        lc.end_at = now
        lc.answered_at = now - timedelta(seconds=random.randint(15, min(lc.duration_sec, 180)))
        lc.started_at = lc.answered_at - timedelta(seconds=lc.ring_sec)
    rows = _setup_cdrs(lc)
    if not lc.failed:
        mid = lc.answered_at + timedelta(seconds=lc.duration_sec * 0.35)
        if lc.with_transfer:
            rows.extend(_transfer_cdrs(lc, mid))
        if lc.with_voicemail:
            rows.extend(_voicemail_cdrs(lc, lc.answered_at + timedelta(seconds=lc.duration_sec * 0.55)))
        rows.extend(_teardown_cdrs(lc, lc.end_at))
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
                details=f"{meta.label} detected — correlated SIP events in telemetry window.",
            )
        )
        session.commit()
    logger.info("Injected %s (%s) anomaly burst", anomaly_key, meta.severity)
