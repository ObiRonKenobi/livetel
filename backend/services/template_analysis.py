"""Rule-based incident analysis for low-memory deployments (no LLM required)."""

from services.anomalies import ANOMALIES


def template_analysis(anomaly: str, data: dict[str, float]) -> str:
    label = ANOMALIES[anomaly].label if anomaly in ANOMALIES else anomaly.replace("_", " ").title()
    root = template_root_cause(anomaly, label)
    mit = template_mitigation(anomaly)
    return (
        f"{label.upper()} — LiveTel analysis engine\n\n"
        f"Telemetry (60s): MOS {data.get('avg_mos', 0):.2f}, latency {data['avg_latency']:.0f} ms, "
        f"jitter {data['avg_jitter']:.0f} ms, loss {data['avg_packet_loss']:.1f}%, "
        f"SIP errors {data['sip_error_rate']:.1f}%.\n\n"
        f"Root cause: {root}\n\n"
        f"Immediate mitigation:\n{mit}"
    )


def template_root_cause(anomaly: str, label: str | None = None) -> str:
    causes = {
        "carrier_outage": "Upstream carrier or SIP trunk peer unreachable — elevated 5xx/408 responses.",
        "toll_fraud": "Abnormal burst to premium-rate destinations — possible PBX compromise or credential abuse.",
        "trunk_exhaustion": "All available SIP trunk channels consumed — new INVITEs receiving 503 Service Unavailable.",
        "auth_failure": "Spike in SIP 401/403 responses — failed registration or digest authentication attempts.",
        "congestion": "WAN or SBC backhaul saturated — queue buildup and elevated loss on RTP paths.",
        "latency_spike": "End-to-end RTT exceeded baseline — routing change, peering issue, or oversubscribed link.",
        "mos_degradation": "Mean Opinion Score dropped below acceptable threshold — codec impairment or buffer bloat.",
        "one_way_audio": "Asymmetric packet loss on media leg — one RTP direction likely blocked or policed.",
        "suspicious_international": "Unusual international destination mix vs. baseline — review LCR and account usage.",
        "dns_sip_failure": "SIP transaction timeouts (408) — DNS resolution failure or unreachable downstream proxy.",
    }
    return causes.get(anomaly, f"Network event consistent with {label or anomaly}.")


def template_mitigation(anomaly: str) -> str:
    steps = {
        "carrier_outage": "1. Open carrier NOC ticket.\n2. Failover to alternate trunk group.\n3. Enable SIP OPTIONS health probes.\n4. Notify customers if MOU > 5 min.",
        "toll_fraud": "1. Block premium/fraud prefixes at SBC.\n2. Rotate compromised credentials.\n3. Enable geo-fencing.\n4. Contact carrier fraud desk.",
        "trunk_exhaustion": "1. Increase trunk capacity or enable overflow route.\n2. Rate-limit new INVITEs per source IP.\n3. Shed non-critical outbound campaigns.",
        "auth_failure": "1. Inspect auth logs for brute-force sources.\n2. Block offending IPs at firewall.\n3. Enforce strong SIP digest secrets.",
        "congestion": "1. Enable adaptive codec (G.729).\n2. Rate-limit new calls on congested routes.\n3. Shift 30% traffic to secondary carrier.",
        "latency_spike": "1. Traceroute affected paths.\n2. Verify no recent routing policy changes.\n3. Consider temporary traffic shift.",
        "mos_degradation": "1. Inspect RTP stats per trunk.\n2. Check for oversubscription on edge SBC.\n3. Validate DSCP/QoS marking end-to-end.",
        "one_way_audio": "1. Capture RTP on both legs.\n2. Check firewall pinholes and symmetric RTP settings.\n3. Verify NAT binding timeouts.",
        "suspicious_international": "1. Compare CDR mix to 7-day baseline.\n2. Require PIN for international destinations.\n3. Alert account managers for top talkers.",
        "dns_sip_failure": "1. Verify internal DNS resolver health.\n2. Check SRV records for SIP domains.\n3. Failover to secondary outbound proxy.",
    }
    return steps.get(anomaly, "1. Review NOC dashboard.\n2. Escalate per runbook.\n3. Document timeline for post-incident review.")
