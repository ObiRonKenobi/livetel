"""Rule-based SIP incident write-ups for the NOC dashboard."""

from services.anomalies import ANOMALIES, LEGACY_KEY_MAP


def _normalize_key(anomaly: str) -> str:
    return LEGACY_KEY_MAP.get(anomaly, anomaly)


def template_analysis(anomaly: str, data: dict[str, float]) -> str:
    key = _normalize_key(anomaly)
    label = ANOMALIES[key].label if key in ANOMALIES else key.replace("_", " ").title()
    root = template_root_cause(key, label)
    mit = template_mitigation(key)
    return (
        f"{label.upper()} — SIP telemetry\n\n"
        f"Signaling window (60s): MOS {data.get('avg_mos', 0):.2f}, latency {data['avg_latency']:.0f} ms, "
        f"jitter {data['avg_jitter']:.0f} ms, RTP loss {data['avg_packet_loss']:.1f}%, "
        f"SIP error rate {data['sip_error_rate']:.1f}%.\n\n"
        f"Root cause: {root}\n\n"
        f"Immediate mitigation:\n{mit}"
    )


def template_root_cause(anomaly: str, label: str | None = None) -> str:
    key = _normalize_key(anomaly)
    causes = {
        "sip_trunk_unreachable": "Upstream SIP trunk peer unreachable — elevated 5xx/408 on INVITE and OPTIONS.",
        "toll_fraud": "Abnormal SIP INVITE burst to premium-rate destinations — possible credential abuse.",
        "sip_503_overload": "SBC or softphone pool returning 503 — concurrent session or registration limit hit.",
        "auth_failure": "Spike in SIP 401/403 — failed digest auth or softphone registration attempts.",
        "rtp_packet_loss": "WAN or edge link saturated — RTP queue buildup and elevated media loss.",
        "sip_latency_spike": "SIP transaction RTT exceeded baseline — routing or peering degradation.",
        "codec_quality_drop": "MOS below threshold — codec impairment, jitter buffer underruns, or oversubscribed SBC.",
        "one_way_audio": "Asymmetric RTP loss on one media leg — firewall, NAT, or one-way pinhole issue.",
        "softphone_registration_failure": "WebRTC/softphone clients failing REGISTER — web app signaling or WSS proxy fault.",
        "sip_dns_timeout": "SIP 408 timeouts — SRV/A record resolution failure or unreachable outbound proxy.",
    }
    return causes.get(key, f"SIP event pattern consistent with {label or key}.")


def template_mitigation(anomaly: str) -> str:
    key = _normalize_key(anomaly)
    steps = {
        "sip_trunk_unreachable": "1. Open carrier NOC ticket.\n2. Failover to alternate SIP trunk group.\n3. Enable SIP OPTIONS health probes.\n4. Notify tenants if outage exceeds 5 min.",
        "toll_fraud": "1. Block premium prefixes at SBC.\n2. Rotate compromised SIP credentials.\n3. Enable geo-fencing on outbound dial plans.",
        "sip_503_overload": "1. Raise concurrent call cap or enable overflow route.\n2. Rate-limit new INVITEs per source IP.\n3. Shed non-critical outbound dialer campaigns.",
        "auth_failure": "1. Inspect REGISTER/INVITE auth logs.\n2. Block brute-force source IPs.\n3. Enforce strong digest secrets on softphones.",
        "rtp_packet_loss": "1. Enable narrow-band codec on congested routes.\n2. Verify QoS/DSCP on RTP paths.\n3. Shift traffic to secondary WAN link.",
        "sip_latency_spike": "1. Traceroute affected SIP paths.\n2. Verify no recent routing policy changes.\n3. Temporarily shift softphone traffic to alternate POP.",
        "codec_quality_drop": "1. Inspect per-trunk RTP MOS stats.\n2. Check SBC CPU and licensing limits.\n3. Validate end-to-end QoS marking.",
        "one_way_audio": "1. Capture RTP on both call legs.\n2. Check symmetric RTP and firewall pinholes.\n3. Verify NAT binding timeouts on softphone subnets.",
        "softphone_registration_failure": "1. Check web softphone WSS gateway and cert expiry.\n2. Verify STUN/TURN reachability from user browsers.\n3. Restart registration cluster if health checks fail.",
        "sip_dns_timeout": "1. Verify internal DNS resolver health.\n2. Check SRV records for SIP domains.\n3. Failover to secondary outbound proxy.",
    }
    return steps.get(key, "1. Review SIP CDR stream.\n2. Escalate per NOC runbook.\n3. Document timeline for post-incident review.")
