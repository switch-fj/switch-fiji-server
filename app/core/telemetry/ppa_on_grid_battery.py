from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.telemetry.base import (
    ClientTelemetryModel,
    GatewayTelemetryModel,
    TimestampTelemetryModel,
)


class PPAOnGridBatteryTelemetryMeterModel(BaseModel):
    slave_id: int
    description: Literal[
        "grid_meter",
        "essential_loads_meter",
        "non_essential_loads_meter",
        "generator_meter",
    ]

    v1: float
    v2: float
    v3: float

    i1: float
    i2: float
    i3: float

    kw_total: float
    kva_total: float
    kvar_total: float
    pf_total: float
    freq_hz: float

    # optional energy fields (not all meters have them)
    kwh_import: Optional[float] = None
    kwh_export: Optional[float] = None
    kwh_total: Optional[float] = None

    # generator-specific split energy
    kwh_t1: Optional[float] = None
    kwh_t2: Optional[float] = None

    kw1: Optional[float] = None
    kw2: Optional[float] = None
    kw3: Optional[float] = None


class PPAOnGridBatteryTelemetryInverterModel(BaseModel):
    slave_id: int
    status: str

    battery_soc: float
    battery_voltage_v: float
    battery_current_a: float
    battery_power_w: float
    battery_state: str
    battery_temp_c: float

    pv1_power_w: float
    pv2_power_w: float
    pv_total_w: float

    load_l1_w: float
    load_l2_w: float
    load_l3_w: float
    load_total_w: float

    grid_v_l1: float
    grid_v_l2: float
    grid_v_l3: float
    freq_hz: float


class PPAOnGridBatteryTelemetryGeneratorModel(BaseModel):
    status: str
    relay_state: int
    confirmed_running: bool

    runtime_minutes: int

    start_trigger: Optional[str] = None
    soc_at_start: Optional[float] = None


class PPAOnGridBatteryTelemetryModel(BaseModel):
    client: ClientTelemetryModel
    gateway: GatewayTelemetryModel
    timestamp: TimestampTelemetryModel

    meters: List[PPAOnGridBatteryTelemetryMeterModel] = Field(default_factory=List)
    inverters: List[PPAOnGridBatteryTelemetryInverterModel] = Field(default_factory=List)

    generator: PPAOnGridBatteryTelemetryGeneratorModel
