import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.core.logger import setup_logger
from app.modules.billing.schema import (
    OnGridEnergyItem,
    OnGridNoBatteryEnergyData,
    OnGridNoBatteryEnergyMix,
    OnGridNoBatteryExtractedMeters,
)
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import (
    OnGridNoBatterySlotEnum,
    OnGridNoBatteryTariffSlotModel,
    TariffIndexedRuleTypeEnum,
    TariffSlotTypeEnum,
)
from app.modules.contracts.wizard.base import BaseContractWizard
from app.modules.devices.model import Device
from app.modules.devices.schema import MeterRoleEnum
from app.modules.invoices.model import InvoiceSnapshot
from app.modules.invoices.schema import (
    BaseInvoiceLineItemModel,
    BaseInvoiceMeterDataModel,
    CreateInvoiceModel,
)
from app.modules.settings.model import ContractSettings

logger = setup_logger(__name__)


class PPAOnGridNoBatteryContractWizard(BaseContractWizard):
    def __init__(
        self,
        energy_data: OnGridNoBatteryEnergyData,
        start_meters: OnGridNoBatteryExtractedMeters,
        end_meters: OnGridNoBatteryExtractedMeters,
        telemetry_start_reading: dict,
        telemetry_end_reading: dict,
        solar_tariff: OnGridNoBatteryTariffSlotModel,
        grid_tariff: OnGridNoBatteryTariffSlotModel,
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        self.energy_data = energy_data
        self.start_meters = start_meters
        self.end_meters = end_meters
        self.telemetry_start_reading = telemetry_start_reading
        self.telemetry_end_reading = telemetry_end_reading
        self.solar_tariff = solar_tariff
        self.grid_tariff = grid_tariff
        self.contract = contract
        self.devices = devices
        self.contract_settings = contract_settings

    @classmethod
    def _extract_meters(cls, telemetry_data: dict):
        grid_meter = None
        solar_meters = []

        meters: list[dict] = telemetry_data.get("meters", [])

        if not len(meters):
            raise ValueError("PPA On-grid No Battery telemetry data has empty meter data")

        for meter in meters:
            description = meter.get("description")
            if description == MeterRoleEnum.GRID_METER.value:
                grid_meter = meter

            if description == MeterRoleEnum.SOLAR_METER.value:
                solar_meters.append(meter)

        return OnGridNoBatteryExtractedMeters(grid_meter=grid_meter, solar_meters=solar_meters)

    @property
    def energy_mix(self):
        solar_energy_kwh = 0
        grid_energy_kwh_import = self.energy_data.grid_import.usage

        for el in self.energy_data.solar:
            solar_energy_kwh += el.usage

        return OnGridNoBatteryEnergyMix(
            solar=float(f"{solar_energy_kwh:.2f}"),
            grid=float(f"{grid_energy_kwh_import:.2f}"),
        )

    @property
    def solar_rate(self):
        tariff_indexed_rule_type = self.contract.details.tariff_indexed_rule_type
        efl_standard_rate_kwh = self.contract_settings.efl_standard_rate_kwh

        if self.solar_tariff.slot_type == TariffSlotTypeEnum.FIXED:
            solar_rate = Decimal(str(self.solar_tariff.rate))
        else:
            rate = Decimal(str(self.solar_tariff.rate))

            if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.EFL_LINKED:  # ✅
                multiplier = (Decimal(100) + rate) / Decimal(100)
                solar_rate = Decimal(efl_standard_rate_kwh * multiplier).quantize(Decimal("0.01"))
            elif tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.FIXED_ANNUAL_ESCALATOR:
                raise NotImplementedError(...)
            else:
                raise ValueError(f"Unsupported tariff_indexed_rule_type: {tariff_indexed_rule_type}")

        return solar_rate.quantize(Decimal("0.01"))

    @property
    def subtotal(self):
        solar_meters_subtotal = Decimal("0")
        for m in self.energy_data.solar:
            solar_meters_subtotal += Decimal(str(m.usage)) * self.solar_rate

        return solar_meters_subtotal.quantize(Decimal("0.01"))

    def invoice(
        self,
        period_start_at: datetime,
        period_end_at: datetime,
        contract_uid: UUID,
        invoice_ref: str,
    ):
        subtotal = self.subtotal
        energy_mix = self.energy_mix
        vat_rate = self.contract_settings.vat_rate
        efl_standard_rate_kwh = self.contract_settings.efl_standard_rate_kwh

        create_invoice_model: CreateInvoiceModel = CreateInvoiceModel(
            period_start_at=period_start_at,
            period_end_at=period_end_at,
            period_start_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_start_reading)),
            period_end_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_end_reading)),
            subtotal=subtotal,
            vat_rate=vat_rate,
            efl_standard_rate_kwh=efl_standard_rate_kwh,
            energy_mix=energy_mix.model_dump_json(),
        ).model_dump()

        create_invoice_model["contract_uid"] = contract_uid
        create_invoice_model["invoice_ref"] = invoice_ref

        return create_invoice_model

    def invoice_snapshot(
        self,
        period_start_at: datetime,
        period_end_at: datetime,
    ):
        return InvoiceSnapshot(
            period_start_at=period_start_at,
            period_end_at=period_end_at,
            period_start_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_start_reading)),
            period_end_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_end_reading)),
            subtotal=self.subtotal,
            vat_rate=self.contract_settings.vat_rate,
            efl_standard_rate_kwh=self.contract_settings.efl_standard_rate_kwh,
            energy_mix=self.energy_mix.model_dump_json(),
        )

    @property
    def invoice_line_items(self):
        create_invoice_line_items: list[BaseInvoiceLineItemModel] = [
            BaseInvoiceLineItemModel(
                description="Grid Import (not charged)",
                energy_kwh=Decimal(str(self.energy_data.grid_import.usage)),
                tariff_rate=Decimal("0.0"),
                tariff_slot=self.grid_tariff.slot,
                tariff_period=int(self.grid_tariff.period_number),
                amount=Decimal("0.0"),
            )
        ]

        for solar_meter in self.energy_data.solar:
            energy_kwh = Decimal(str(solar_meter.usage))
            create_invoice_line_items.append(
                BaseInvoiceLineItemModel(
                    description=f"Solar Meter {solar_meter.slave_id}",
                    energy_kwh=energy_kwh,
                    tariff_rate=self.solar_rate,
                    tariff_slot=self.solar_tariff.slot,
                    tariff_period=int(self.solar_tariff.period_number),
                    amount=energy_kwh * self.solar_rate,
                )
            )

        return create_invoice_line_items

    @property
    def invoice_meter_data(
        self,
    ):
        create_invoice_meter_data: list[BaseInvoiceMeterDataModel] = []
        for device in self.devices:
            for solar in self.energy_data.solar:
                if device.slave_id == solar.slave_id:
                    create_invoice_meter_data.append(
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=f"Solar meter {device.slave_id}",
                            period_telemetry_start_reading=Decimal(solar.start_kwh),
                            period_telemetry_end_reading=Decimal(solar.end_kwh),
                        )
                    )

            if device.slave_id == self.energy_data.grid_import.slave_id:
                create_invoice_meter_data.append(
                    BaseInvoiceMeterDataModel(
                        device_uid=device.uid,
                        label="Grid meter",
                        period_telemetry_start_reading=Decimal(self.energy_data.grid_import.start_kwh),
                        period_telemetry_end_reading=Decimal(self.energy_data.grid_import.end_kwh),
                    )
                )

        return create_invoice_meter_data

    @classmethod
    def factory(
        cls,
        telemetry_start_reading: dict,
        telemetry_end_reading: dict,
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        # start period
        start_meters: OnGridNoBatteryExtractedMeters = cls._extract_meters(telemetry_data=telemetry_start_reading)
        start_grid_meter = start_meters.grid_meter
        start_solar_meter = start_meters.solar_meters

        # end period
        end_meters: OnGridNoBatteryExtractedMeters = cls._extract_meters(telemetry_data=telemetry_end_reading)
        end_grid_meter = end_meters.grid_meter
        end_solar_meter = end_meters.solar_meters

        solar = [
            OnGridEnergyItem(
                slave_id=start["slave_id"],
                description=start["description"],
                start_kwh=start["kwh_import"],
                end_kwh=end["kwh_import"],
            )
            for start, end in zip(start_solar_meter, end_solar_meter)
        ]

        grid_import = OnGridEnergyItem(
            slave_id=end_grid_meter["slave_id"],
            description="Grid Meter",
            start_kwh=start_grid_meter["kwh_import"],
            end_kwh=end_grid_meter["kwh_import"],
        )
        grid_export = OnGridEnergyItem(
            slave_id=start_grid_meter["slave_id"],
            description="Fed to Grid",
            start_kwh=start_grid_meter["kwh_export"],
            end_kwh=end_grid_meter["kwh_export"],
        )

        energy_data = OnGridNoBatteryEnergyData(solar=solar, grid_import=grid_import, grid_export=grid_export)

        contract_tariffs = [
            OnGridNoBatteryTariffSlotModel.model_validate(tariff)
            for tariff in json.loads(contract.details.ppa_on_grid_no_battery_tariffs)
        ]

        for tariff in contract_tariffs:
            if tariff.slot == OnGridNoBatterySlotEnum.SOLAR.value:
                solar_tariff = tariff
            else:
                grid_tariff = tariff

        return cls(
            energy_data=energy_data,
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            start_meters=start_meters,
            end_meters=end_meters,
            solar_tariff=solar_tariff,
            grid_tariff=grid_tariff,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )
