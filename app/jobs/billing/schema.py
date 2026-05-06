from pydantic import BaseModel, ConfigDict

from app.modules.contracts.schema import OnGridNoBatteryTariffSlotModel


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
    solar_rate: float
    subtotal: float
