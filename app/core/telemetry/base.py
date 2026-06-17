from pydantic import BaseModel


class ClientTelemetryModel(BaseModel):
    client_name: str
    client_email: str
    client_id: str
    site_id: str


class GatewayTelemetryModel(BaseModel):
    gateway_id: str
    firmware: str


class TimestampTelemetryModel(BaseModel):
    ts_epoch_ms: int
