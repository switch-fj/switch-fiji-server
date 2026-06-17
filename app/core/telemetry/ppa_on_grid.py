from typing import List, Optional, Union

from pydantic import BaseModel, Field

from app.core.telemetry.base import (
    ClientTelemetryModel,
    GatewayTelemetryModel,
    TimestampTelemetryModel,
)


class PPAOnGridNoBatteryTelemetryMeterModel(BaseModel):
    slave_id: int
    description: str

    v1: float
    v2: float
    v3: float

    i1: float
    i2: float
    i3: float

    pf_total: float
    freq_hz: float

    kwh_import: Optional[float] = None
    kwh_export: Optional[float] = None
    kwh_total: Optional[float] = None

    kvarh_import: Optional[float] = None
    kvarh_export: Optional[float] = None

    kw_total: Union[float, str]
    kva_total: Union[float, str]
    kvar_total: Union[float, str]


class PPAOnGridNoBatteryTelemetryModel(BaseModel):
    gateway: GatewayTelemetryModel
    gateway_id: str

    client: ClientTelemetryModel
    timestamp: TimestampTelemetryModel

    meters: List[PPAOnGridNoBatteryTelemetryMeterModel] = Field(default_factory=list)

    ts_epoch_ms: int
