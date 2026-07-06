from pydantic import BaseModel


class MetricsResponse(BaseModel):
    active_calls: int
    avg_latency: float
    avg_jitter: float
    avg_packet_loss: float
    avg_mos: float
    error_codes: dict[str, int]


class CdrResponse(BaseModel):
    id: int
    time: str
    call_id: str
    direction: str
    sip_method: str
    from_uri: str
    to_uri: str
    duration: int
    mos: float
    latency: float
    jitter: float
    packet_loss: float
    sip_code: int
    leg: int


class SipFlowResponse(BaseModel):
    call_id: str
    events: list[CdrResponse]


class AlertResponse(BaseModel):
    id: int
    time: str
    type: str
    severity: str
    details: str


class AlertContextResponse(BaseModel):
    alert: AlertResponse
    related_events: list[CdrResponse]
    root_cause: str
    mitigation: str


class HealthResponse(BaseModel):
    status: str
    db: bool
    ollama: bool
