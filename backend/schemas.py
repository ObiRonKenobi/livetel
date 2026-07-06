from pydantic import BaseModel


class MetricsResponse(BaseModel):
    active_calls: int
    avg_latency: float
    avg_jitter: float
    avg_packet_loss: float
    avg_mos: float
    error_codes: dict[str, int]


class CdrResponse(BaseModel):
    time: str
    src: str
    dst: str
    duration: int
    mos: float
    latency: float
    jitter: float
    packet_loss: float
    sip_code: int


class AlertResponse(BaseModel):
    time: str
    type: str
    details: str


class HealthResponse(BaseModel):
    status: str
    db: bool
    ollama: bool
