from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.core.telemetry.ppa_off_grid import PPAOffGridTelemetryMeterModel
from app.core.telemetry.ppa_on_grid import PPAOnGridNoBatteryTelemetryMeterModel
from app.modules.contracts.schema import OnGridNoBatteryTariffSlotModel


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
        value = self.end_day_tariff - self.start_day_tariff

        return float(f"{value:.2f}")

    @computed_field
    @property
    def night_usage(self) -> float:
        value = self.end_night_tariff - self.start_night_tariff

        return float(f"{value:.2f}")

    @computed_field
    @property
    def usage(self) -> float:
        day_value = self.end_day_tariff - self.start_day_tariff
        night_value = self.end_night_tariff - self.start_night_tariff
        value = day_value + night_value

        return float(f"{value:.2f}")


class PPAOffGridExtractedMeters(BaseModel):
    gen_meter: PPAOffGridTelemetryMeterModel
    load_meter: PPAOffGridTelemetryMeterModel


class PPAOffGridEnergyData(BaseModel):
    load: PPAOnAndOffGridEnergyItem
    backup_gen: PPAOnAndOffGridEnergyItem


class PPAOffGridEnergyMix(BaseModel):
    """Computed billing-period energy mix for all load meter and the gen meter."""

    load: float
    backup_gen: float


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
    grid_meter: Optional[PPAOnGridNoBatteryTelemetryMeterModel] = None


class OnGridWithBatterExtractedMeters(OnGridMeters):
    essential_loads_meter: Optional[dict] = None
    non_essential_loads_meter: Optional[dict] = None
    generator_meter: Optional[dict] = None


class OnGridWithBatteryEnergyMix(BaseModel):
    """Computed billing-period energy mix for all solar meters and the grid meter."""

    solar: float
    generator: float
    grid: float


class OnGridEnergyItem(BaseModel):
    slave_id: Optional[int]
    description: str
    start_kwh: float
    end_kwh: float

    @computed_field
    @property
    def usage(self) -> float:
        value = self.end_kwh - self.start_kwh

        return float(f"{value:.2f}")


class OnGridWithBatteryEnergyData(BaseModel):
    essential: PPAOnAndOffGridEnergyItem
    non_essential: PPAOnAndOffGridEnergyItem
    grid_import: PPAOnAndOffGridEnergyItem
    grid_export: PPAOnAndOffGridEnergyItem
    generator: PPAOnAndOffGridEnergyItem


class OnGridNoBatteryExtractedMeters(OnGridMeters):
    solar_meters: list[PPAOnGridNoBatteryTelemetryMeterModel] = []


class OnGridNoBatteryEnergyData(BaseModel):
    solar: list[OnGridEnergyItem]
    grid_import: OnGridEnergyItem
    grid_export: OnGridEnergyItem
