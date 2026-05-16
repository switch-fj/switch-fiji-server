import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.core.logger import setup_logger
from app.modules.billing.schema import (
    OnGridEnergyItem,
    OnGridWithBatterExtractedMeters,
    OnGridWithBatteryEnergyData,
    OnGridWithBatteryEnergyMix,
    PPAOnAndOffGridEnergyItem,
)
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import (
    TariffIndexedRuleTypeEnum,
    TariffSlotModel,
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
    InvoiceLineItemEnum,
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

        essesntial = OnGridEnergyItem(
            slave_id=essential_loads_meter_t1["slave_id"],
            description="Essential Energy",
            start_kwh=essential_loads_meter_t1["kwh_total"],
            end_kwh=essential_loads_meter_t2["kwh_total"],
        )
        non_essential = OnGridEnergyItem(
            slave_id=non_essential_loads_meter_t1["slave_id"],
            description="Non-Essential Energy",
            start_kwh=non_essential_loads_meter_t1["kwh_total"],
            end_kwh=non_essential_loads_meter_t2["kwh_total"],
        )
        grid_import = OnGridEnergyItem(
            slave_id=grid_meter_t1["slave_id"],
            description="Grid Energy",
            start_kwh=grid_meter_t1["kwh_import"],
            end_kwh=grid_meter_t2["kwh_import"],
        )
        grid_export = OnGridEnergyItem(
            slave_id=grid_meter_t1["slave_id"],
            description="Fed to Grid",
            start_kwh=grid_meter_t1["kwh_export"],
            end_kwh=grid_meter_t2["kwh_export"],
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
            essential=essesntial,
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

    def calculate_rate(self, tariff_slot: dict):
        tariff_indexed_rule_type = self.contract.details.tariff_indexed_rule_type
        efl_standard_rate_kwh = self.contract_settings.efl_standard_rate_kwh

        if tariff_slot["slot_type"] == TariffSlotTypeEnum.FIXED:
            return Decimal(str(tariff_slot["rate"]))

        rate = Decimal(str(tariff_slot["rate"]))
        if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.EFL_LINKED:
            multiplier = (Decimal(100) + rate) / Decimal(100)
            return Decimal(efl_standard_rate_kwh * multiplier).quantize(Decimal("0.01"))
        if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.FIXED_ANNUAL_ESCALATOR:
            raise NotImplementedError("FIXED_ANNUAL_ESCALATOR is not yet supported for PPA off-grid tariff")
        raise ValueError(f"Unsupported tariff_indexed_rule_type: {tariff_indexed_rule_type}")

    def _total_facility_consumption(self, essential_loads_meter: dict, non_essential_loads_meter: dict):
        essential_load_kwh = essential_loads_meter.get("kwh_total", 0)
        non_essential_load_kwh = non_essential_loads_meter.get("kwh_total", 0)

        return float(essential_load_kwh + non_essential_load_kwh)

    def _net_grid_contribution(self, grid_meter: dict):

        kwh_import = grid_meter.get("kwh_import", 0)
        kwh_export = grid_meter.get("kwh_export", 0)

        return float(kwh_import - kwh_export)

    def _net_grid_import(self, kwh_import_t1: int, kwh_import_t2: int):
        return float(kwh_import_t2 - kwh_import_t1)

    def _net_grid_export(self, kwh_export_t1: int, kwh_export_t2: int):
        return float(kwh_export_t2 - kwh_export_t1)

    def _delta_facility_consumption(self, fc_t1: float, fc_t2: float):
        return fc_t2 - fc_t1

    def _delta_net_grid_contribution(self, ngc_t1: float, ngc_t2: float):
        return ngc_t2 - ngc_t1

    def billable_energy_kwh(self):
        extracted_meters_t1 = self.extracted_meters_t1
        grid_meter_t1 = extracted_meters_t1.grid_meter
        extracted_meters_t1
        essential_loads_meter_t1 = extracted_meters_t1.essential_loads_meter
        non_essential_loads_meter_t1 = extracted_meters_t1.non_essential_loads_meter

        fc_t1 = self._total_facility_consumption(
            essential_loads_meter=essential_loads_meter_t1,
            non_essential_loads_meter=non_essential_loads_meter_t1,
        )
        ngc_t1 = self._net_grid_contribution(grid_meter=grid_meter_t1)

        # end period (T2)
        extracted_meters_t2 = self.extracted_meters_t2
        grid_meter_t2 = extracted_meters_t2.grid_meter
        essential_loads_meter_t2 = extracted_meters_t2.essential_loads_meter
        non_essential_loads_meter_t2 = extracted_meters_t2.non_essential_loads_meter

        fc_t2 = self._total_facility_consumption(
            essential_loads_meter=essential_loads_meter_t2,
            non_essential_loads_meter=non_essential_loads_meter_t2,
        )
        ngc_t2 = self._net_grid_contribution(grid_meter=grid_meter_t2)

        # 3. Compute Deltas
        delta_fc = self._delta_facility_consumption(fc_t1=fc_t1, fc_t2=fc_t2)
        delta_ngc = self._delta_net_grid_contribution(ngc_t1=ngc_t1, ngc_t2=ngc_t2)

        energy_used_kwh = max(0.0, delta_fc - delta_ngc)

        # Data integrity check (e.g., if a meter was swapped out/reset to 0)
        if delta_fc < 0 or grid_meter_t2["kwh_import"] < grid_meter_t1["kwh_import"]:
            raise ValueError("Negative consumption detected. Meter may have been reset.")

        return energy_used_kwh

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
            subtotal=self.subtotal,
            vat_rate=self.contract_settings.vat_rate,
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
            subtotal=self.subtotal,
            vat_rate=self.contract_settings.vat_rate,
            efl_standard_rate_kwh=self.contract_settings.efl_standard_rate_kwh,
            energy_mix=self.energy_mix.model_dump_json(),
        )

    @property
    def energy_mix(self):
        solar_usage = self.energy_data.essential.usage
        battery_usage = self.energy_data.non_essential.usage
        grid_import_usage = self.energy_data.grid_import.usage

        return OnGridWithBatteryEnergyMix(
            solar=solar_usage,
            grid=grid_import_usage,
            battery=battery_usage,
        )

    @property
    def tariff_slots(self):
        tariffs: list[TariffSlotModel] = json.loads(self.contract.details.tariff_slots)

        return tariffs

    @property
    def solar_tariff(self):
        return self.tariff_slots[2]

    @property
    def solar_rate(self):
        return self.calculate_rate(tariff_slot=self.solar_tariff)

    @property
    def day_utility_tariff(self):
        return self.tariff_slots[0]

    @property
    def day_utility_rate(self):
        return self.calculate_rate(tariff_slot=self.day_utility_tariff)

    @property
    def night_utility_tariff(self):
        return self.tariff_slots[1]

    @property
    def night_utility_rate(self):
        return self.calculate_rate(tariff_slot=self.night_utility_tariff)

    @property
    def battery_utility_tariff(self):
        return self.tariff_slots[3]

    @property
    def battery_rate(self):
        return self.calculate_rate(tariff_slot=self.battery_utility_tariff)

    @property
    def solar_energy_cost(self):
        return two_decimal_place(self.energy_data.essential.usage * self.solar_rate)

    @property
    def battery_energy_cost(self):
        return two_decimal_place(self.energy_data.non_essential.usage * self.battery_rate)

    @property
    def generator_day_energy_cost(self):
        day_usage_cost = self.energy_data.generator.day_usage * self.day_utility_rate

        return two_decimal_place(day_usage_cost)

    @property
    def generator_night_energy_cost(self):
        night_usage_cost = self.energy_data.generator.night_usage * self.night_utility_rate

        return two_decimal_place(night_usage_cost)

    @property
    def subtotal(self):
        return (
            self.battery_energy_cost
            + self.solar_energy_cost
            + self.generator_day_energy_cost
            + self.generator_night_energy_cost
        )

    @property
    def invoice_line_items(self):
        create_invoice_line_items = [
            BaseInvoiceLineItemModel(
                description=InvoiceLineItemEnum.ESSENTIAL_ENERGY_SUPPLIED.value,
                energy_kwh=Decimal(self.energy_data.essential.usage),
                tariff_rate=Decimal(self.solar_tariff.rate),
                tariff_slot=self.solar_tariff.slot,
                tariff_period=int(self.solar_tariff.period_number),
                amount=Decimal(self.solar_energy_cost),
            ),
            BaseInvoiceLineItemModel(
                description=InvoiceLineItemEnum.NON_ESSENTIAL_ENERGY_SUPPLIED.value,
                energy_kwh=Decimal(self.energy_data.non_essential.usage),
                tariff_rate=Decimal(self.battery_utility_tariff.rate),
                tariff_slot=self.battery_utility_tariff.slot,
                tariff_period=int(self.battery_utility_tariff.period_number),
                amount=Decimal(self.battery_energy_cost),
            ),
            BaseInvoiceLineItemModel(
                description=f"{InvoiceLineItemEnum.GENERATOR_ENERGY_SUPPLIED.value} Day",
                energy_kwh=Decimal(self.energy_data.generator.day_usage),
                tariff_rate=Decimal(self.day_utility_tariff.rate),
                tariff_slot=self.day_utility_tariff.slot,
                tariff_period=int(self.day_utility_tariff.period_number),
                amount=Decimal(self.generator_day_energy_cost),
            ),
            BaseInvoiceLineItemModel(
                description=f"{InvoiceLineItemEnum.GENERATOR_ENERGY_SUPPLIED.value} Night",
                energy_kwh=Decimal(self.energy_data.generator.night_usage),
                tariff_rate=Decimal(self.night_utility_tariff.rate),
                tariff_slot=self.night_utility_tariff.slot,
                tariff_period=int(self.night_utility_tariff.period_number),
                amount=Decimal(self.generator_night_energy_cost),
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
                create_invoice_meter_data.append(
                    BaseInvoiceMeterDataModel(
                        device_uid=device.uid,
                        label=InvoiceMeterLabelEnum.ESSENTIAL_LOAD_GENRATION.value,
                        period_start_reading=Decimal(self.energy_data.essential.start_kwh),
                        period_end_reading=Decimal(self.energy_data.essential.end_kwh),
                    ),
                )

            if device.slave_id == self.energy_data.non_essential.slave_id:
                create_invoice_meter_data.append(
                    BaseInvoiceMeterDataModel(
                        device_uid=device.uid,
                        label=InvoiceMeterLabelEnum.NON_ESSENTIAL_LOAD_GENRATION.value,
                        period_start_reading=Decimal(self.energy_data.non_essential.start_kwh),
                        period_end_reading=Decimal(self.energy_data.non_essential.end_kwh),
                    ),
                )

            if device.slave_id == self.energy_data.generator.slave_id:
                create_invoice_meter_data.extend(
                    [
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.GEN_METER_DAY.value,
                            period_start_reading=Decimal(self.energy_data.generator.start_day_tariff),
                            period_end_reading=Decimal(self.energy_data.generator.end_day_tariff),
                        ),
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.GEN_METER_NIGHT.value,
                            period_start_reading=Decimal(self.energy_data.generator.start_night_tariff),
                            period_end_reading=Decimal(self.energy_data.generator.end_night_tariff),
                        ),
                    ]
                )

        return create_invoice_meter_data
