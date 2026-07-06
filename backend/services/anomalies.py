"""SIP and softphone anomaly types with severity tiers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnomalyDef:
    key: str
    severity: str  # critical | warning
    label: str


ANOMALIES: dict[str, AnomalyDef] = {
    "sip_trunk_unreachable": AnomalyDef("sip_trunk_unreachable", "critical", "SIP Trunk Unreachable"),
    "toll_fraud": AnomalyDef("toll_fraud", "critical", "SIP Toll Fraud"),
    "sip_503_overload": AnomalyDef("sip_503_overload", "critical", "SIP 503 — Service Unavailable"),
    "auth_failure": AnomalyDef("auth_failure", "critical", "SIP Auth Failure"),
    "rtp_packet_loss": AnomalyDef("rtp_packet_loss", "warning", "RTP Packet Loss"),
    "sip_latency_spike": AnomalyDef("sip_latency_spike", "warning", "SIP Latency Spike"),
    "codec_quality_drop": AnomalyDef("codec_quality_drop", "warning", "Codec Quality Drop"),
    "one_way_audio": AnomalyDef("one_way_audio", "warning", "One-Way Audio (RTP)"),
    "softphone_registration_failure": AnomalyDef(
        "softphone_registration_failure", "warning", "Softphone Registration Failure"
    ),
    "sip_dns_timeout": AnomalyDef("sip_dns_timeout", "warning", "SIP DNS / Timeout"),
}

CRITICAL_KEYS = [k for k, v in ANOMALIES.items() if v.severity == "critical"]
WARNING_KEYS = [k for k, v in ANOMALIES.items() if v.severity == "warning"]

# Legacy keys from older deployments (map to current types for templates)
LEGACY_KEY_MAP: dict[str, str] = {
    "carrier_outage": "sip_trunk_unreachable",
    "trunk_exhaustion": "sip_503_overload",
    "congestion": "rtp_packet_loss",
    "latency_spike": "sip_latency_spike",
    "mos_degradation": "codec_quality_drop",
    "dns_sip_failure": "sip_dns_timeout",
    "suspicious_international": "toll_fraud",
}
