from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.telemetry.base import (
    ClientTelemetryModel,
    GatewayTelemetryModel,
    TimestampTelemetryModel,
)


class PPAOffGridTelemetryACTemperatureUnitModel(BaseModel):
    temperature_c: float
    slave_id: int
    status: str


class PPAOffGridTelemetryTariffModel(BaseModel):
    kwh_t1: float
    kwh_t2: float


class PPAOffGridTelemetryMeterModel(BaseModel):
    slave_id: int
    description: Literal["gen_meter", "load_meter", "aux_loads", "micro_inv"]

    p_total_w: float
    kwh_total: float

    i1: float
    i2: float
    i3: float

    p1_w: float
    p2_w: float
    p3_w: float

    v1: float
    v2: float
    v3: float

    freq_hz: Optional[float] = None
    tariff: Optional[PPAOffGridTelemetryTariffModel] = None


class PPAOffGridTelemetryIrradianceMeterModel(BaseModel):
    slave_id: int
    irradiance_w_per_m2: float


class PPAOffGridTelemetryInverterModel(BaseModel):
    slave_id: int
    status: str

    p_total_w: float
    freq_hz: float

    battery_soc: float
    battery_power_w: float
    battery_current_a: float

    pv1_v: float
    pv1_i: float
    pv1_w: float

    pv2_v: float
    pv2_i: float
    pv2_w: float

    pv3_v: float
    pv3_i: float
    pv3_w: float

    pv4_v: float
    pv4_i: float
    pv4_w: float

    battery_soc2: Optional[float] = None


class PPAOffGridTelemetryModel(BaseModel):
    gateway_id: str
    ts_epoch_ms: int

    gateway: GatewayTelemetryModel
    client: ClientTelemetryModel
    timestamp: TimestampTelemetryModel

    ac_units: List[PPAOffGridTelemetryACTemperatureUnitModel] = Field(default_factory=List)
    meters: List[PPAOffGridTelemetryMeterModel] = Field(default_factory=List)
    irradiance_meters: List[PPAOffGridTelemetryIrradianceMeterModel] = Field(default_factory=List)
    inverters: List[PPAOffGridTelemetryInverterModel] = Field(default_factory=List)
