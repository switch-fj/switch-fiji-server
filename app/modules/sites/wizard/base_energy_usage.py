import re
from abc import ABC, abstractmethod
from datetime import time

from pydantic import BaseModel, ConfigDict


class BaseEnergyUsageWizard(ABC):
    TOTAL_POWER_KEY = "p_total_w"
    BATTERY_POWER_KEY = "battery_power_w"
    BATTERY_SOC_PATTERN = re.compile(r"^battery_soc(\d*)$")
    PV_POWER_PATTERN = re.compile(r"^pv(\d+)_w$")

    @abstractmethod
    def _extract_meters(self, telemetry_data: dict): ...

    @abstractmethod
    def _extract_inverters(self, telemetry_data: dict): ...

    @abstractmethod
    def compute_energy_usage(self): ...


class EnergyUsageDataPoint(BaseModel):
    solar: float
    battery: float
    battery_flow: float
    grid: float
    consumption: float
    aux_loads: float
    micro_inv: float
    soc: dict[str, float]


class PPAEnergyUsageItem(BaseModel):
    time_at: time
    data: EnergyUsageDataPoint | None = None

    model_config = ConfigDict(from_attributes=True)
