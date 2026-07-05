"""Rule-based incident analysis for low-memory deployments (no LLM required)."""


def template_analysis(anomaly: str, data: dict[str, float]) -> str:
    lat = data["avg_latency"]
    jitter = data["avg_jitter"]
    pl = data["avg_packet_loss"]
    err = data["sip_error_rate"]
    unusual = data["unusual_dest_ratio"]

    if anomaly == "congestion":
        return (
            f"CONGESTION DETECTED — LiveTel analysis engine\n\n"
            f"Telemetry (60s window): latency {lat:.0f} ms (elevated), jitter {jitter:.0f} ms, "
            f"packet loss {pl:.1f}%, SIP error rate {err:.1f}%.\n\n"
            f"Root cause: WAN or SBC backhaul is saturated — likely bandwidth exhaustion, "
            f"queue buildup on edge routers, or ISP peering congestion during a traffic spike.\n\n"
            f"Immediate mitigation:\n"
            f"1. Enable adaptive codec negotiation (G.729/G.722) on affected trunks.\n"
            f"2. Rate-limit new call setups on congested routes.\n"
            f"3. Failover 30% of traffic to secondary carrier.\n"
            f"4. Alert NOC — if loss exceeds 10%, consider controlled trunk shutdown."
        )

    if anomaly == "carrier_outage":
        return (
            f"CARRIER OUTAGE DETECTED — LiveTel analysis engine\n\n"
            f"Telemetry (60s window): SIP error rate {err:.1f}% (critical), latency {lat:.0f} ms, "
            f"packet loss {pl:.1f}%.\n\n"
            f"Root cause: Upstream carrier or SIP trunk peer is unreachable or rejecting sessions — "
            f"elevated 4xx/5xx responses (503/408) indicate gateway timeout or provider-side failure.\n\n"
            f"Immediate mitigation:\n"
            f"1. Verify carrier NOC status page and open ticket with trunk provider.\n"
            f"2. Route outbound via alternate LCR (least-cost routing) path.\n"
            f"3. Enable SIP OPTIONS health checks on affected gateways.\n"
            f"4. Notify customers if MOU exceeds 5 min — prepare IVR failover message."
        )

    if anomaly == "toll_fraud":
        return (
            f"TOLL FRAUD PATTERN DETECTED — LiveTel analysis engine\n\n"
            f"Telemetry (60s window): unusual-destination ratio {unusual:.0%} (threshold 20%), "
            f"avg call duration elevated, latency {lat:.0f} ms.\n\n"
            f"Root cause: Abnormal burst of calls to high-cost or non-standard destinations (XYZ prefix) — "
            f"consistent with PBX compromise, credential stuffing, or fraudulent call pump.\n\n"
            f"Immediate mitigation:\n"
            f"1. Block XYZ destination prefix at SBC immediately.\n"
            f"2. Disable compromised SIP credentials; force password rotation.\n"
            f"3. Enable geo-fencing on international routes.\n"
            f"4. Contact carrier fraud desk — request trunk suspension if spend anomaly confirmed."
        )

    return f"Anomaly '{anomaly}' detected. Review NOC dashboard and escalate per runbook."
