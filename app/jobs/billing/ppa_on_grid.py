import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.jobs.billing.schema import (
    OnGridNoBatteryEnergyMix,
    PPAOnGridEnergyItem,
    PPAOnGridNoBatteryEnergyData,
    PPAOnGridNoBatteryExtractedMeters,
)
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import (
    OnGridNoBatterySlotEnum,
    OnGridNoBatteryTariffSlotModel,
    TariffIndexedRuleTypeEnum,
    TariffSlotTypeEnum,
)
from app.modules.devices.model import Device
from app.modules.invoices.schema import CreateInvoiceModel
from app.modules.settings.model import ContractSettings


class PPAOnGridNoBatteryEngine:
    def __init__(
        self,
        energy_data: PPAOnGridNoBatteryEnergyData,
        start_meters: PPAOnGridNoBatteryExtractedMeters,
        end_meters: PPAOnGridNoBatteryExtractedMeters,
        start_reading: dict,
        end_reading: dict,
        solar_tariff: OnGridNoBatteryTariffSlotModel,
        grid_tariff: OnGridNoBatteryTariffSlotModel,
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        self.energy_data = energy_data
        self.start_meters = start_meters
        self.end_meters = end_meters
        self.start_reading = start_reading
        self.end_reading = end_reading
        self.solar_tariff = solar_tariff
        self.grid_tariff = grid_tariff
        self.contract = contract
        self.devices = devices
        self.contract_settings = contract_settings

    @classmethod
    def _extract_meters(cls, reading: dict):
        grid_meter = None
        solar_meters = []

        meters = reading.get("meters", [])

        for meter in meters:
            if meter.get("grid_meter", None):
                grid_meter = meter.get("grid_meter")

            if meter.get("solar_meter", None):
                solar_meters.append(meter.get("solar_meter"))

        return PPAOnGridNoBatteryExtractedMeters(grid_meter=grid_meter, solar_meters=solar_meters)

    @property
    def energy_mix(self):
        solar_energy_kwh = 0
        grid_energy_kwh_import = self.energy_data.grid_import.usage

        for el in self.energy_data.solar:
            solar_energy_kwh += el.usage

        return OnGridNoBatteryEnergyMix(
            solar=float(f"{float(solar_energy_kwh):.2f}"),
            grid=float(f"{float(grid_energy_kwh_import):.2f}"),
        )

    @property
    def solar_rate(self):
        tariff_indexed_rule_type = self.contract.details.tariff_indexed_rule_type
        efl_standard_rate_kwh = self.contract_settings.efl_standard_rate_kwh

        if self.solar_tariff.get("slot_type") == TariffSlotTypeEnum.FIXED:
            solar_rate = Decimal(str(self.solar_tariff.get("rate")))
        else:
            rate = Decimal(str(self.solar_tariff.get("rate")))

            if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.FIXED_ANNUAL_ESCALATOR:
                multiplier = (Decimal(100) + rate) / Decimal(100)
                solar_rate = (efl_standard_rate_kwh * multiplier).quantize(Decimal("0.01"))
            elif tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.FIXED_ANNUAL_ESCALATOR:
                raise NotImplementedError(
                    "FIXED_ANNUAL_ESCALATOR is not yet supported for PPA on-grid no-battery solar tariff"
                )
            else:
                raise ValueError(f"Unsupported tariff_indexed_rule_type: {tariff_indexed_rule_type}")

        return solar_rate.quantize(Decimal("0.01"))

    def calculate_subtotal(self, solar_rate: Decimal):
        solar_meters_subtotal = Decimal("0")
        for m in self.energy_data.solar:
            solar_meters_subtotal += Decimal(str(m.usage)) * solar_rate

        return solar_meters_subtotal.quantize(Decimal("0.01"))

    def compute_invoice_model(
        self,
        period_start_at: datetime,
        period_end_at: datetime,
        contract_uid: UUID,
        invoice_ref: str,
    ):
        solar_rate = self.solar_rate
        subtotal = self.calculate_subtotal(solar_rate=solar_rate)
        energy_mix = self.energy_mix
        vat_rate = self.contract_settings.vat_rate
        efl_standard_rate_kwh = self.contract_settings.efl_standard_rate_kwh

        create_invoice_model: CreateInvoiceModel = CreateInvoiceModel(
            period_start_at=period_start_at,
            period_end_at=period_end_at,
            period_start_telemetry_data=json.dumps(jsonable_encoder(self.start_reading)),
            period_end_telemetry_data=json.dumps(jsonable_encoder(self.end_reading)),
            subtotal=subtotal,
            vat_rate=vat_rate,
            efl_standard_rate_kwh=efl_standard_rate_kwh,
            energy_mix=energy_mix,
        ).model_dump()

        create_invoice_model["contract_uid"] = contract_uid
        create_invoice_model["invoice_ref"] = invoice_ref

        return create_invoice_model

    def compute_invoice_line_items(self):
        pass

    def compute_invoice_meter_data(self):
        pass

    @classmethod
    def factory(
        cls,
        start_reading: dict,
        end_reading: dict,
        contract_tariffs: list[OnGridNoBatteryTariffSlotModel],
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        # start period
        start_meters: PPAOnGridNoBatteryExtractedMeters = cls._extract_meters(reading=start_reading)
        start_grid_meter = start_meters.grid_meter
        start_solar_meter = start_meters.solar_meters

        # end period
        end_meters: PPAOnGridNoBatteryExtractedMeters = cls._extract_meters(reading=end_reading)
        end_grid_meter = end_meters.grid_meter
        end_solar_meter = end_meters.solar_meters

        solar = [
            PPAOnGridEnergyItem(
                slave_id=start["slave_id"],
                description=start["description"],
                start_kwh=start["kwh_import"],
                end_kwh=end["kwh_import"],
            )
            for start, end in zip(start_solar_meter, end_solar_meter)
        ]

        grid_import = PPAOnGridEnergyItem(
            slave_id=end_grid_meter["slave_id"],
            description="Grid Meter",
            start_kwh=start_grid_meter["kwh_import"],
            end_kwh=end_grid_meter["kwh_import"],
        )
        grid_export = PPAOnGridEnergyItem(
            description="Fed to Grid",
            start_kwh=start_grid_meter["kwh_export"],
            end_kwh=end_grid_meter["kwh_export"],
        )

        energy_data = PPAOnGridNoBatteryEnergyData(solar=solar, grid_import=grid_import, grid_export=grid_export)

        for tariff in contract_tariffs:
            if tariff.get("slot") == OnGridNoBatterySlotEnum.SOLAR.value:
                solar_tariff = tariff
            else:
                grid_tariff = tariff

        return cls(
            energy_data=energy_data,
            start_reading=start_reading,
            end_reading=end_reading,
            start_meters=start_meters,
            end_meters=end_meters,
            solar_tariff=solar_tariff,
            grid_tariff=grid_tariff,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )
