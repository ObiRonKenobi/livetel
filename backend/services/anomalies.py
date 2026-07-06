"""Anomaly types with severity tiers for injection and detection."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalyDef:
    key: str
    severity: str  # critical | warning
    label: str


ANOMALIES: dict[str, AnomalyDef] = {
    "carrier_outage": AnomalyDef("carrier_outage", "critical", "Carrier Outage"),
    "toll_fraud": AnomalyDef("toll_fraud", "critical", "Toll Fraud"),
    "trunk_exhaustion": AnomalyDef("trunk_exhaustion", "critical", "Trunk Exhaustion"),
    "auth_failure": AnomalyDef("auth_failure", "critical", "SIP Auth Failure"),
    "congestion": AnomalyDef("congestion", "warning", "Network Congestion"),
    "latency_spike": AnomalyDef("latency_spike", "warning", "Latency Spike"),
    "mos_degradation": AnomalyDef("mos_degradation", "warning", "MOS Degradation"),
    "one_way_audio": AnomalyDef("one_way_audio", "warning", "One-Way Audio"),
    "suspicious_international": AnomalyDef("suspicious_international", "warning", "Suspicious International"),
    "dns_sip_failure": AnomalyDef("dns_sip_failure", "warning", "DNS / SIP Timeout"),
}

CRITICAL_KEYS = [k for k, v in ANOMALIES.items() if v.severity == "critical"]
WARNING_KEYS = [k for k, v in ANOMALIES.items() if v.severity == "warning"]
