from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.modules.contracts.schema import OnGridNoBatteryTariffSlotModel

# off grif schema


class PPAOnAndOffGridEnergyItem(BaseModel):
    slave_id: int
    description: str
    start_day_tariff: float
    start_night_tariff: float
    end_day_tariff: float
    end_night_tariff: float

    @computed_field
    @property
    def day_usage(self) -> float:
        return float(f"{self.end_day_tariff - self.start_day_tariff}")

    @computed_field
    @property
    def night_usage(self) -> float:
        return float(f"{self.start_night_tariff - self.end_night_tariff}")


class PPAOffGridExtractedMeters:
    gen_meter: dict
    load_meter: dict


class PPAOffGridNoBatteryEnergyData(BaseModel):
    load: PPAOnAndOffGridEnergyItem
    gen: PPAOnAndOffGridEnergyItem


class PPAOffGridEnergyMix(BaseModel):
    """Computed billing-period energy mix for all load meter and the gen meter."""

    load: float
    gen: float


# ==============================


class OnGridMeterImportReading(BaseModel):
    """Single meter entry from a DynamoDB periodic reading (on-grid no battery)."""

    slave_id: int
    description: str | None = None
    kwh_import: float = 0
    kvarh_import: float = 0

    model_config = ConfigDict(extra="allow")


class OnGridPeriodicEnergyData(BaseModel):
    """Top-level DynamoDB reading parsed for on-grid no battery billing."""

    meters: list[OnGridMeterImportReading] = []

    model_config = ConfigDict(extra="allow")


class OnGridNoBatteryMeterImportData(BaseModel):
    """Period-boundary import snapshot: all solar meters + single grid meter."""

    solar_meter_kwh_kvarh_import: list[OnGridMeterImportReading]
    gen_meter_kwh_kvarh_import: OnGridMeterImportReading


class MeterImportUsage(BaseModel):
    """Billing-period usage delta (end − start) for a single meter."""

    slave_id: int
    description: str | None = None
    kwh_import_usage: float
    kvarh_import_usage: float


class OnGridNoBatteryUsage(BaseModel):
    """Computed billing-period usage for all solar meters and the grid meter."""

    solar_meters_import_usage: list[MeterImportUsage]
    grid_meter_import_usage: MeterImportUsage


class OnGridNoBatteryEnergyMix(BaseModel):
    """Computed billing-period energy mix for all solar meters and the grid meter."""

    solar: float
    grid: float


class ComputePPAOnGridNoBatteryInvoiceResp(BaseModel):
    create_invoice_dict: dict
    period_start_meters_import_data: OnGridNoBatteryMeterImportData
    period_end_meters_import_data: OnGridNoBatteryMeterImportData
    usage: OnGridNoBatteryUsage
    solar_tariff: OnGridNoBatteryTariffSlotModel
    grid_tariff: OnGridNoBatteryTariffSlotModel
    solar_rate: Decimal
    subtotal: Decimal


# New schemas for contract type billing calculation


class OnGridMeters(BaseModel):
    grid_meter: Optional[dict] = None


class OnGridWithBatterExtractedMeters(OnGridMeters):
    essential_loads_meter: Optional[dict] = None
    non_essential_loads_meter: Optional[dict] = None
    generator_meter: Optional[dict] = None


class OnGridWithBatteryEnergyMix(BaseModel):
    """Computed billing-period energy mix for all solar meters and the grid meter."""

    solar: float
    grid_export: float
    grid_import: float


class OnGridEnergyItem(BaseModel):
    slave_id: Optional[int]
    description: str
    start_kwh: float
    end_kwh: float

    @computed_field
    @property
    def usage(self) -> float:
        return float(f"{self.end_kwh - self.start_kwh}")


class OnGridWithBatteryEnergyData(BaseModel):
    essential: OnGridEnergyItem
    non_essential: OnGridEnergyItem
    grid_import: OnGridEnergyItem
    grid_export: OnGridEnergyItem
    generator: PPAOnAndOffGridEnergyItem


class OnGridNoBatteryExtractedMeters(OnGridMeters):
    solar_meters: list[dict] = []


class OnGridNoBatteryEnergyData(BaseModel):
    solar: list[OnGridEnergyItem]
    grid_import: OnGridEnergyItem
    grid_export: OnGridEnergyItem
