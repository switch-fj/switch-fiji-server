import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.core.logger import setup_logger
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import (
    TariffIndexedRuleTypeEnum,
    TariffSlotModel,
    TariffSlotTypeEnum,
)
from app.modules.contracts.wizard.base import BaseContractWizard
from app.modules.contracts.wizard.schema import (
    OnGridWithBatterExtractedMeters,
    OnGridWithBatteryEnergyData,
    OnGridWithBatteryEnergyMix,
    PPAOnAndOffGridEnergyItem,
)
from app.modules.devices.model import Device
from app.modules.devices.schema import MeterRoleEnum
from app.modules.invoices.model import InvoiceSnapshot
from app.modules.invoices.schema import (
    BaseInvoiceLineItemModel,
    BaseInvoiceMeterDataModel,
    CreateInvoiceModel,
    InvoiceMeterLabelEnum,
)
from app.modules.settings.model import ContractSettings
from app.utils import two_decimal_place

logger = setup_logger(__name__)


class PPAOnGridWithBatteryContractWizard(BaseContractWizard):
    def __init__(
        self,
        energy_data: OnGridWithBatteryEnergyData,
        extracted_meters_t1: OnGridWithBatterExtractedMeters,
        extracted_meters_t2: OnGridWithBatterExtractedMeters,
        telemetry_start_reading: dict,
        telemetry_end_reading: dict,
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        self.energy_data = energy_data
        self.extracted_meters_t1 = extracted_meters_t1
        self.extracted_meters_t2 = extracted_meters_t2
        self.telemetry_start_reading = telemetry_start_reading
        self.telemetry_end_reading = telemetry_end_reading
        self.contract = contract
        self.devices = devices
        self.contract_settings = contract_settings

    @classmethod
    def _extract_meters(cls, telemetry_data: dict):
        grid_meter = None
        essential_loads_meter = None
        non_essential_loads_meter = None
        generator_meter = None
        meters: list[dict] = telemetry_data.get("meters", [])

        for meter in meters:
            description = meter.get("description", "")
            if description == MeterRoleEnum.GRID_METER.value:
                grid_meter = meter

            if description == MeterRoleEnum.ESSENTIAL_LOAD.value:
                essential_loads_meter = meter

            if description == MeterRoleEnum.NON_ESSENTIAL_LOAD.value:
                non_essential_loads_meter = meter

            if description == MeterRoleEnum.GENERATOR_METER.value:
                generator_meter = meter

        return OnGridWithBatterExtractedMeters.model_validate(
            {
                "grid_meter": grid_meter,
                "essential_loads_meter": essential_loads_meter,
                "non_essential_loads_meter": non_essential_loads_meter,
                "generator_meter": generator_meter,
            }
        )

    @classmethod
    def _validate_meters(cls, extracted: OnGridWithBatterExtractedMeters, period: str):
        missing = []

        if extracted.grid_meter is None:
            missing.append("grid_meter")
        if extracted.essential_loads_meter is None:
            missing.append("essential_loads_meter")
        if extracted.non_essential_loads_meter is None:
            missing.append("non_essential_loads_meter")
        if extracted.generator_meter is None:
            missing.append("generator_meter")

        if missing:
            raise ValueError(
                f"Missing required meters in telemetry data for period {period}: "
                f"{', '.join(missing)}. Check meter role descriptions in the telemetry payload."
            )

    @classmethod
    def factory(
        cls,
        telemetry_start_reading: dict,
        telemetry_end_reading: dict,
        contract: Contract,
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        # start period (T1)
        extracted_meters_t1: OnGridWithBatterExtractedMeters = cls._extract_meters(
            telemetry_data=telemetry_start_reading
        )
        grid_meter_t1 = extracted_meters_t1.grid_meter
        essential_loads_meter_t1 = extracted_meters_t1.essential_loads_meter
        non_essential_loads_meter_t1 = extracted_meters_t1.non_essential_loads_meter
        generator_meter_t1 = extracted_meters_t1.generator_meter

        # end period (T2)
        extracted_meters_t2: OnGridWithBatterExtractedMeters = cls._extract_meters(telemetry_data=telemetry_end_reading)
        grid_meter_t2 = extracted_meters_t2.grid_meter
        essential_loads_meter_t2 = extracted_meters_t2.essential_loads_meter
        non_essential_loads_meter_t2 = extracted_meters_t2.non_essential_loads_meter
        generator_meter_t2 = extracted_meters_t2.generator_meter

        cls._validate_meters(extracted_meters_t1, period="T1 (start)")
        cls._validate_meters(extracted_meters_t2, period="T2 (end)")

        essential = PPAOnAndOffGridEnergyItem(
            slave_id=essential_loads_meter_t1["slave_id"],
            description="Essential Energy",
            start_day_tariff=essential_loads_meter_t1["kwh_t1"],
            start_night_tariff=essential_loads_meter_t1["kwh_t2"],
            end_day_tariff=essential_loads_meter_t2["kwh_t1"],
            end_night_tariff=essential_loads_meter_t2["kwh_t2"],
        )
        non_essential = PPAOnAndOffGridEnergyItem(
            slave_id=non_essential_loads_meter_t1["slave_id"],
            description="Non-Essential Energy",
            start_day_tariff=non_essential_loads_meter_t1["kwh_t1"],
            start_night_tariff=non_essential_loads_meter_t1["kwh_t2"],
            end_day_tariff=non_essential_loads_meter_t2["kwh_t1"],
            end_night_tariff=non_essential_loads_meter_t2["kwh_t2"],
        )
        grid_import = PPAOnAndOffGridEnergyItem(
            slave_id=grid_meter_t1["slave_id"],
            description="Grid Energy",
            start_day_tariff=grid_meter_t1["kwh_import_t1"],
            start_night_tariff=grid_meter_t1["kwh_import_t2"],
            end_day_tariff=grid_meter_t2["kwh_import_t1"],
            end_night_tariff=grid_meter_t2["kwh_import_t2"],
        )
        grid_export = PPAOnAndOffGridEnergyItem(
            slave_id=grid_meter_t1["slave_id"],
            description="Fed to Grid",
            start_day_tariff=grid_meter_t1["kwh_export_t1"],
            start_night_tariff=grid_meter_t1["kwh_export_t2"],
            end_day_tariff=grid_meter_t2["kwh_export_t1"],
            end_night_tariff=grid_meter_t2["kwh_export_t2"],
        )
        generator = PPAOnAndOffGridEnergyItem(
            slave_id=generator_meter_t1["slave_id"],
            description="Generator",
            start_day_tariff=generator_meter_t1["kwh_t1"],
            start_night_tariff=generator_meter_t1["kwh_t2"],
            end_day_tariff=generator_meter_t2["kwh_t1"],
            end_night_tariff=generator_meter_t2["kwh_t2"],
        )

        energy_data = OnGridWithBatteryEnergyData(
            essential=essential,
            non_essential=non_essential,
            grid_import=grid_import,
            grid_export=grid_export,
            generator=generator,
        )

        return cls(
            energy_data=energy_data,
            extracted_meters_t1=extracted_meters_t1,
            extracted_meters_t2=extracted_meters_t2,
            telemetry_start_reading=telemetry_start_reading,
            telemetry_end_reading=telemetry_end_reading,
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

    def calculate_rate(self, tariff_slot: TariffSlotModel):
        tariff_indexed_rule_type = self.contract.details.tariff_indexed_rule_type
        efl_standard_rate_kwh = self.contract_settings.efl_standard_rate_kwh

        if tariff_slot.slot_type == TariffSlotTypeEnum.FIXED:
            return Decimal(str(tariff_slot.rate))

        rate = Decimal(str(tariff_slot.rate))
        if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.EFL_LINKED:
            multiplier = (Decimal(100) + rate) / Decimal(100)
            return Decimal(efl_standard_rate_kwh * multiplier).quantize(Decimal("0.01"))
        elif tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.FIXED_ANNUAL_ESCALATOR:
            raise NotImplementedError("FIXED_ANNUAL_ESCALATOR is not yet supported for PPA off-grid tariff")
        raise ValueError(f"Unsupported tariff_indexed_rule_type: {tariff_indexed_rule_type}")

    def invoice(
        self,
        period_start_at: datetime,
        period_end_at: datetime,
        contract_uid: UUID,
        invoice_ref: str,
    ):
        create_invoice_model: CreateInvoiceModel = CreateInvoiceModel(
            period_start_at=period_start_at,
            period_end_at=period_end_at,
            period_start_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_start_reading)),
            period_end_telemetry_data=json.dumps(jsonable_encoder(self.telemetry_end_reading)),
            subtotal=self.energy_cost,
            vat_rate=two_decimal_place(self.contract_settings.vat_rate),
            efl_standard_rate_kwh=self.contract_settings.efl_standard_rate_kwh,
            energy_mix=self.energy_mix.model_dump_json(),
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
            subtotal=self.energy_cost,
            vat_rate=two_decimal_place(self.contract_settings.vat_rate),
            efl_standard_rate_kwh=self.contract_settings.efl_standard_rate_kwh,
            energy_mix=self.energy_mix.model_dump_json(),
        )

    @property
    def energy_mix(self):
        solar_usage = self.energy_data.non_essential.usage + self.energy_data.essential.usage
        grid_import_usage = self.energy_data.grid_import.usage
        generator_usage = self.energy_data.generator.usage

        return OnGridWithBatteryEnergyMix(
            solar=solar_usage,
            generator=generator_usage,
            grid=grid_import_usage,
        )

    @property
    def active_tariff_slots(self):
        active_tariff_slots = self.contract.details.active_tariff_slots

        return [TariffSlotModel.model_validate(tariff) for tariff in active_tariff_slots]

    @property
    def day_tariff(self):
        return self.active_tariff_slots[0]

    @property
    def night_tariff(self):
        return self.active_tariff_slots[1]

    @property
    def night_energy_rate(self):
        return self.calculate_rate(tariff_slot=self.night_tariff)

    @property
    def day_energy_rate(self):
        return self.calculate_rate(tariff_slot=self.day_tariff)

    @property
    def billable_day_energy_kwh(self):
        return (
            self.energy_data.essential.day_usage
            + self.energy_data.non_essential.day_usage
            - (self.energy_data.generator.day_usage + self.energy_data.grid_import.day_usage)
        )

    @property
    def billable_night_energy_kwh(self):
        return (
            self.energy_data.essential.night_usage
            + self.energy_data.non_essential.night_usage
            - (self.energy_data.generator.night_usage + self.energy_data.grid_import.night_usage)
        )

    @property
    def day_energy_cost(self):
        return (Decimal(self.billable_day_energy_kwh) * self.day_energy_rate).quantize(Decimal("0.01"))

    @property
    def night_energy_cost(self):
        return (Decimal(self.billable_night_energy_kwh) * self.night_energy_rate).quantize(Decimal("0.01"))

    @property
    def energy_cost(self):
        return self.day_energy_cost + self.night_energy_cost

    @property
    def billable_energy_kwh(self):
        solar_consumed_kwh = self.billable_day_energy_kwh + self.billable_night_energy_kwh

        grid_import_usage = self.energy_data.grid_import.usage
        generator_usage = self.energy_data.generator.usage

        if solar_consumed_kwh < 0 or grid_import_usage < 0 or generator_usage < 0:
            raise ValueError("Negative energy delta detected. Potential meter reset event.")

        return max(0.0, solar_consumed_kwh)

    @property
    def invoice_line_items(self):
        create_invoice_line_items = [
            BaseInvoiceLineItemModel(
                description="Billable Day Energy",
                energy_kwh=Decimal(self.billable_day_energy_kwh),
                tariff_rate=self.day_energy_rate,
                tariff_slot=self.day_tariff.slot,
                tariff_period=int(self.day_tariff.period_number),
                amount=Decimal(self.day_energy_cost),
            ),
            BaseInvoiceLineItemModel(
                description="Billable Night Energy",
                energy_kwh=Decimal(self.billable_night_energy_kwh),
                tariff_rate=Decimal(self.night_energy_rate),
                tariff_slot=self.night_tariff.slot,
                tariff_period=int(self.night_tariff.period_number),
                amount=Decimal(self.night_energy_cost),
            ),
        ]

        return create_invoice_line_items

    @property
    def invoice_meter_data(
        self,
    ):
        create_invoice_meter_data: list[BaseInvoiceMeterDataModel] = []
        for device in self.devices:
            if device.slave_id == self.energy_data.essential.slave_id:
                create_invoice_meter_data.extend(
                    [
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=f"{InvoiceMeterLabelEnum.ESSENTIAL_LOAD_GENRATION.value} Day",
                            period_start_reading=Decimal(self.energy_data.essential.start_day_tariff),
                            period_end_reading=Decimal(self.energy_data.essential.end_day_tariff),
                        ),
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=f"{InvoiceMeterLabelEnum.ESSENTIAL_LOAD_GENRATION.value} Night",
                            period_start_reading=Decimal(self.energy_data.essential.start_night_tariff),
                            period_end_reading=Decimal(self.energy_data.essential.end_night_tariff),
                        ),
                    ]
                )

            if device.slave_id == self.energy_data.non_essential.slave_id:
                create_invoice_meter_data.extend(
                    [
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=f"{InvoiceMeterLabelEnum.NON_ESSENTIAL_LOAD_GENRATION.value} Day",
                            period_start_reading=Decimal(self.energy_data.non_essential.start_day_tariff),
                            period_end_reading=Decimal(self.energy_data.non_essential.end_day_tariff),
                        ),
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=f"{InvoiceMeterLabelEnum.NON_ESSENTIAL_LOAD_GENRATION.value} Night",
                            period_start_reading=Decimal(self.energy_data.non_essential.start_night_tariff),
                            period_end_reading=Decimal(self.energy_data.non_essential.end_night_tariff),
                        ),
                    ]
                )

            if device.slave_id == self.energy_data.generator.slave_id:
                create_invoice_meter_data.extend(
                    [
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=f"{InvoiceMeterLabelEnum.GEN_METER_DAY.value} (Not billed)",
                            period_start_reading=Decimal(self.energy_data.generator.start_day_tariff),
                            period_end_reading=Decimal(self.energy_data.generator.end_day_tariff),
                        ),
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=f"{InvoiceMeterLabelEnum.GEN_METER_NIGHT.value} (Not billed)",
                            period_start_reading=Decimal(self.energy_data.generator.start_night_tariff),
                            period_end_reading=Decimal(self.energy_data.generator.end_night_tariff),
                        ),
                    ]
                )

        return create_invoice_meter_data
