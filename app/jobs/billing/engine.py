import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from dateutil.relativedelta import relativedelta
from fastapi.encoders import jsonable_encoder

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client
from app.jobs.billing.schema import (
    ComputePPAOnGridNoBatteryInvoiceResp,
    MeterImportUsage,
    OnGridMeterImportReading,
    OnGridNoBatteryEnergyMix,
    OnGridNoBatteryMeterImportData,
    OnGridNoBatteryUsage,
    OnGridPeriodicEnergyData,
)
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import (
    ContractBillingFrequencyEnum,
    OnGridNoBatterySlotEnum,
    OnGridNoBatteryTariffSlotModel,
    TariffIndexedRuleTypeEnum,
    TariffSlotTypeEnum,
)
from app.modules.devices.model import Device
from app.modules.devices.schema import MeterRoleEnum
from app.modules.invoices.model import (
    Invoice,
    InvoiceLineItem,
    InvoiceMeterData,
)
from app.modules.invoices.pdf import InvoicePDF
from app.modules.invoices.repository import InvoiceRepository
from app.modules.invoices.schema import (
    BaseInvoiceLineItemModel,
    BaseInvoiceMeterDataModel,
    CreateInvoiceModel,
    InvoiceDetailsDict,
    InvoiceLineItemEnum,
    InvoiceMeterLabelEnum,
)
from app.modules.settings.model import ContractSettings
from app.services.s3 import S3Service
from app.utils import two_decimal_place

logger = setup_logger(__name__)


class BillingEngine:
    @staticmethod
    def _extract_meter_by_description(reading: dict, description: str):
        selected_meter = []
        for meter in reading.get("meters", []):
            if meter.get("description") == description:
                selected_meter.append(meter)
        return selected_meter

    @staticmethod
    def get_current_billing_period(
        commissioned_at: datetime,
        billing_frequency: str,
        as_of: datetime,
    ):

        try:
            freq = ContractBillingFrequencyEnum(billing_frequency.lower())
        except ValueError:
            raise ValueError(f"Unsupported billing frequency: {billing_frequency}")

        diff = relativedelta(as_of, commissioned_at)
        match freq:
            # case ContractBillingFrequencyEnum.WEEKLY:  # for testing purpose
            #     total_seconds = (as_of - commissioned_at).total_seconds()
            #     n = int(total_seconds // (5 * 60))
            #     delta = relativedelta(minutes=5)
            case ContractBillingFrequencyEnum.WEEKLY:
                total_days = (as_of - commissioned_at).days
                n = total_days // 7
                delta = relativedelta(weeks=1)
            case ContractBillingFrequencyEnum.BI_WEEKLY:
                total_days = (as_of - commissioned_at).days
                n = total_days // 14
                delta = relativedelta(weeks=2)
            case ContractBillingFrequencyEnum.MONTHLY:
                total_months = diff.years * 12 + diff.months
                n = total_months // 1
                delta = relativedelta(months=1)
            case ContractBillingFrequencyEnum.QUARTERLY:
                total_months = diff.years * 12 + diff.months
                n = total_months // 3
                delta = relativedelta(months=3)
            case ContractBillingFrequencyEnum.SEMI_ANNUALLY:
                total_months = diff.years * 12 + diff.months
                n = total_months // 6
                delta = relativedelta(months=6)
            case ContractBillingFrequencyEnum.ANNUALLY:
                n = diff.years
                delta = relativedelta(years=1)

        period_start = commissioned_at + (delta * n)
        period_end = period_start + delta - relativedelta(seconds=1)

        return (period_start, period_end)

    @staticmethod
    def get_all_billing_periods(
        commissioned_at: datetime,
        billing_frequency: str,
        as_of: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """Returns all billing periods from commissioned_at up to as_of."""
        # try:
        #     freq = ContractBillingFrequencyEnum(billing_frequency.lower())
        # except ValueError:
        #     raise ValueError(f"Unsupported billing frequency: {billing_frequency}")

        match billing_frequency:
            case "daily":
                delta = relativedelta(days=1)
            case ContractBillingFrequencyEnum.WEEKLY:
                delta = relativedelta(weeks=1)
            case ContractBillingFrequencyEnum.BI_WEEKLY:
                delta = relativedelta(weeks=2)
            case ContractBillingFrequencyEnum.MONTHLY:
                delta = relativedelta(months=1)
            case ContractBillingFrequencyEnum.QUARTERLY:
                delta = relativedelta(months=3)
            case ContractBillingFrequencyEnum.SEMI_ANNUALLY:
                delta = relativedelta(months=6)
            case ContractBillingFrequencyEnum.ANNUALLY:
                delta = relativedelta(years=1)

        periods = []
        period_start = commissioned_at
        while True:
            period_end = period_start + delta - relativedelta(seconds=1)
            if period_end > as_of:
                break
            periods.append((period_start, period_end))
            period_start = period_end + relativedelta(seconds=1)

        return periods

    @staticmethod
    def get_ppa_off_grid_meter_data(
        periodic_energy_data: dict | Any,
    ):
        load_meter = BillingEngine._extract_meter_by_description(
            periodic_energy_data, description=MeterRoleEnum.LOAD_METER
        )
        gen_meter = BillingEngine._extract_meter_by_description(
            periodic_energy_data, description=MeterRoleEnum.GEN_METER
        )

        site_meter_tariff = [
            load_meter[0].get("tariff", 0)["kwh_t1"],
            load_meter[0].get("tariff", 0)["kwh_t2"],
        ]
        gen_meter_tariff = [
            gen_meter[0].get("tariff", 0)["kwh_t1"],
            gen_meter[0].get("tariff", 0)["kwh_t2"],
        ]

        return (
            site_meter_tariff,
            gen_meter_tariff,
        )

    @staticmethod
    def get_ppa_on_grid_no_battery_kwh_kvarh_import_data(
        periodic_energy_data: dict | Any,
    ) -> OnGridNoBatteryMeterImportData:
        parsed = OnGridPeriodicEnergyData.model_validate(periodic_energy_data)

        solar_meters = [m for m in parsed.meters if m.description == MeterRoleEnum.SOLAR_METER]
        grid_meters = [m for m in parsed.meters if m.description == MeterRoleEnum.GRID_METER]

        return OnGridNoBatteryMeterImportData(
            solar_meter_kwh_kvarh_import=[
                OnGridMeterImportReading(
                    slave_id=m.slave_id,
                    description=m.description,
                    kwh_import=m.kwh_import,
                    kvarh_import=m.kvarh_import,
                )
                for m in solar_meters
            ],
            gen_meter_kwh_kvarh_import=OnGridMeterImportReading(
                slave_id=grid_meters[0].slave_id,
                description=grid_meters[0].description,
                kwh_import=grid_meters[0].kwh_import,
                kvarh_import=grid_meters[0].kvarh_import,
            ),
        )

    @staticmethod
    def compute_ppa_on_grid_no_battery_usage(
        period_start_meters_import_data: OnGridNoBatteryMeterImportData,
        period_end_meters_import_data: OnGridNoBatteryMeterImportData,
    ) -> OnGridNoBatteryUsage:
        grid_start = period_start_meters_import_data.gen_meter_kwh_kvarh_import
        grid_end = period_end_meters_import_data.gen_meter_kwh_kvarh_import

        grid_meter_import_usage = MeterImportUsage(
            slave_id=grid_start.slave_id,
            description=grid_start.description,
            kwh_import_usage=grid_end.kwh_import - grid_start.kwh_import,
            kvarh_import_usage=grid_end.kvarh_import - grid_start.kvarh_import,
        )

        solar_meters_import_usage = [
            MeterImportUsage(
                slave_id=start.slave_id,
                description=start.description,
                kwh_import_usage=end.kwh_import - start.kwh_import,
                kvarh_import_usage=end.kvarh_import - start.kvarh_import,
            )
            for start, end in zip(
                period_start_meters_import_data.solar_meter_kwh_kvarh_import,
                period_end_meters_import_data.solar_meter_kwh_kvarh_import,
            )
        ]

        return OnGridNoBatteryUsage(
            solar_meters_import_usage=solar_meters_import_usage,
            grid_meter_import_usage=grid_meter_import_usage,
        )

    @staticmethod
    def compute_ppa_off_grid_day_night_usage(
        period_start_meter_tariff_reading: list,
        period_end_meter_tariff_reading: list,
    ):
        site_meter_day_usage = period_end_meter_tariff_reading[0][0] - period_start_meter_tariff_reading[0][0]
        site_meter_night_usage = period_end_meter_tariff_reading[0][1] - period_start_meter_tariff_reading[0][1]

        gen_meter_day_usage = period_end_meter_tariff_reading[1][0] - period_start_meter_tariff_reading[1][0]
        gen_meter_night_usage = period_end_meter_tariff_reading[1][1] - period_start_meter_tariff_reading[1][1]

        return {
            "site_meter_day_usage": site_meter_day_usage,
            "site_meter_night_usage": site_meter_night_usage,
            "gen_meter_day_usage": gen_meter_day_usage,
            "gen_meter_night_usage": gen_meter_night_usage,
        }

    @staticmethod
    def compute_ppa_off_grid_line_items(usage: dict[str, Any]):
        on_solar_energy_kwh = usage.get("site_meter_day_usage", 0) - usage.get("gen_meter_day_usage", 0)
        off_solar_energy_kwh = usage.get("site_meter_night_usage", 0) - usage.get("gen_meter_night_usage", 0)

        return (on_solar_energy_kwh, off_solar_energy_kwh)

    @staticmethod
    def compute_ppa_on_grid_no_battery_energy_mix(usage: OnGridNoBatteryUsage):

        solar_energy_kwh = 0
        grid_energy_kwh = usage.grid_meter_import_usage.kwh_import_usage

        for el in usage.solar_meters_import_usage:
            solar_energy_kwh += el.kwh_import_usage

        return OnGridNoBatteryEnergyMix(solar=solar_energy_kwh, grid=grid_energy_kwh)

    @staticmethod
    def compute_ppa_off_grid_energy_mix(usage: dict[str, Any]):

        solar_energy_kwh = usage.get("site_meter_day_usage", 0) + usage.get("site_meter_night_usage", 0)
        gen_energy_kwh = usage.get("gen_meter_day_usage", 0) + usage.get("gen_meter_night_usage", 0)

        return (solar_energy_kwh, gen_energy_kwh)

    @staticmethod
    def _resolve_off_grid_slot_rate(
        slot: dict,
        efl_rate_kwh: Decimal,
        tariff_indexed_rule_type: TariffIndexedRuleTypeEnum | None,
    ) -> Decimal:
        if slot["slot_type"] == TariffSlotTypeEnum.FIXED:
            return Decimal(str(slot["rate"]))

        rate = Decimal(str(slot["rate"]))
        if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.EFL_LINKED:
            multiplier = (Decimal(100) + rate) / Decimal(100)
            return (efl_rate_kwh * multiplier).quantize(Decimal("0.01"))
        if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.FIXED_ANNUAL_ESCALATOR:
            raise NotImplementedError("FIXED_ANNUAL_ESCALATOR is not yet supported for PPA off-grid tariff")
        raise ValueError(f"Unsupported tariff_indexed_rule_type: {tariff_indexed_rule_type}")

    @staticmethod
    def compute_ppa_off_grid_subtotal_and_vat_rate(
        on_solar_energy_kwh,
        off_solar_energy_kwh,
        efl_rate_kwh: Decimal,
        tariff_indexed_rule_type: TariffIndexedRuleTypeEnum | None,
        active_tariff: list[dict],
    ):
        on_solar_energy_kwh = Decimal(str(on_solar_energy_kwh))
        off_solar_energy_kwh = Decimal(str(off_solar_energy_kwh))

        day_rate = BillingEngine._resolve_off_grid_slot_rate(active_tariff[0], efl_rate_kwh, tariff_indexed_rule_type)
        night_rate = BillingEngine._resolve_off_grid_slot_rate(active_tariff[1], efl_rate_kwh, tariff_indexed_rule_type)

        on_solar_energy_amount = two_decimal_place(on_solar_energy_kwh * day_rate)
        off_solar_energy_amount = two_decimal_place(off_solar_energy_kwh * night_rate)

        subtotal = two_decimal_place(on_solar_energy_amount + off_solar_energy_amount)

        return (subtotal, on_solar_energy_amount, off_solar_energy_amount)

    @staticmethod
    def compute_ppa_on_grid_no_battery_subtotal(
        solar_meters_import_usage: list[MeterImportUsage],
        tariff_indexed_rule_type: TariffIndexedRuleTypeEnum,
        efl_standard_rate_kwh: Decimal,
        solar_tariff: OnGridNoBatteryTariffSlotModel,
    ):
        if solar_tariff.get("slot_type") == TariffSlotTypeEnum.FIXED:
            solar_rate = Decimal(str(solar_tariff.get("rate")))
        else:
            rate = Decimal(str(solar_tariff.get("rate")))
            if tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.EFL_LINKED:
                multiplier = (Decimal(100) + rate) / Decimal(100)
                solar_rate = (efl_standard_rate_kwh * multiplier).quantize(Decimal("0.01"))
            elif tariff_indexed_rule_type == TariffIndexedRuleTypeEnum.FIXED_ANNUAL_ESCALATOR:
                raise NotImplementedError(
                    "FIXED_ANNUAL_ESCALATOR is not yet supported for PPA on-grid no-battery solar tariff"
                )
            else:
                raise ValueError(f"Unsupported tariff_indexed_rule_type: {tariff_indexed_rule_type}")

        solar_meters_subtotal = Decimal("0")
        for m in solar_meters_import_usage:
            solar_meters_subtotal += Decimal(str(m.kwh_import_usage)) * solar_rate

        return (solar_meters_subtotal.quantize(Decimal("0.01")), solar_rate)

    @staticmethod
    def build_ppa_on_grid_no_battery_invoice_details(
        devices: list[Device],
        contract_settings: ContractSettings,
        computed_ppa_no_battery_invoice_resp: ComputePPAOnGridNoBatteryInvoiceResp,
    ):
        loaded_invoice_dict = computed_ppa_no_battery_invoice_resp.create_invoice_dict
        period_start_meters_import_data = computed_ppa_no_battery_invoice_resp.period_start_meters_import_data
        period_end_meters_import_data = computed_ppa_no_battery_invoice_resp.period_end_meters_import_data
        usage = computed_ppa_no_battery_invoice_resp.usage
        solar_rate = computed_ppa_no_battery_invoice_resp.solar_rate
        solar_tariff = computed_ppa_no_battery_invoice_resp.solar_tariff
        grid_tariff = computed_ppa_no_battery_invoice_resp.grid_tariff
        subtotal = computed_ppa_no_battery_invoice_resp.subtotal

        create_invoice_meter_data: list[BaseInvoiceMeterDataModel] = []
        for device in devices:
            for start, end in zip(
                period_start_meters_import_data.solar_meter_kwh_kvarh_import,
                period_end_meters_import_data.solar_meter_kwh_kvarh_import,
            ):
                if device.slave_id == start.slave_id:
                    create_invoice_meter_data.append(
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=f"Solar Meter {start.slave_id}",
                            period_start_reading=Decimal(start.kwh_import),
                            period_end_reading=Decimal(end.kwh_import),
                        ),
                    )

            if device.slave_id == period_start_meters_import_data.gen_meter_kwh_kvarh_import.slave_id:
                create_invoice_meter_data.append(
                    BaseInvoiceMeterDataModel(
                        device_uid=device.uid,
                        label="Grid Meter",
                        period_start_reading=Decimal(
                            period_start_meters_import_data.gen_meter_kwh_kvarh_import.kwh_import
                        ),
                        period_end_reading=Decimal(period_end_meters_import_data.gen_meter_kwh_kvarh_import.kwh_import),
                    )
                )

        create_invoice_line_items: list[BaseInvoiceLineItemModel] = [
            BaseInvoiceLineItemModel(
                description="Grid meter",
                energy_kwh=Decimal(str(usage.grid_meter_import_usage.kwh_import_usage)),
                tariff_rate=Decimal("0.0"),
                tariff_slot=grid_tariff.slot,
                tariff_period=int(grid_tariff.period_number),
                amount=Decimal("0.0"),
            )
        ]

        for solar_meter in usage.solar_meters_import_usage:
            energy_kwh = Decimal(str(solar_meter.kwh_import_usage))
            create_invoice_line_items.append(
                BaseInvoiceLineItemModel(
                    description=f"Solar Meter {solar_meter.slave_id}",
                    energy_kwh=energy_kwh,
                    tariff_rate=solar_rate,
                    tariff_slot=solar_tariff.slot,
                    tariff_period=int(solar_tariff.period_number),
                    amount=energy_kwh * solar_rate,
                )
            )

        invoice_details_dict = InvoiceDetailsDict(
            subtotal=subtotal,
            vat_rate=contract_settings.vat_rate,
            efl_standard_rate_kwh=contract_settings.efl_standard_rate_kwh,
            invoice_line_items=create_invoice_line_items,
            invoice_meter_data=create_invoice_meter_data,
            energy_mix=loaded_invoice_dict["energy_mix"],
        )

        return invoice_details_dict

    @staticmethod
    def build_ppa_off_grid_invoice_details(
        devices: list[Device],
        contract_settings: ContractSettings,
        active_tariff_slots: list[dict],
        tariff_indexed_rule_type: TariffIndexedRuleTypeEnum | None,
        readings: tuple[dict, dict],
    ):
        period_start_data, period_end_data = readings

        period_start_meter = BillingEngine.get_ppa_off_grid_meter_data(period_start_data)
        period_end_meter = BillingEngine.get_ppa_off_grid_meter_data(period_end_data)

        load_meter = BillingEngine._extract_meter_by_description(period_start_data, MeterRoleEnum.LOAD_METER)[0]
        gen_meter = BillingEngine._extract_meter_by_description(period_start_data, MeterRoleEnum.GEN_METER)[0]

        usage = BillingEngine.compute_ppa_off_grid_day_night_usage(
            period_start_meter_tariff_reading=period_start_meter,
            period_end_meter_tariff_reading=period_end_meter,
        )
        on_solar_energy_kwh, off_solar_energy_kwh = BillingEngine.compute_ppa_off_grid_line_items(usage=usage)
        solar_energy_kwh, gen_energy_kwh = BillingEngine.compute_ppa_off_grid_energy_mix(usage=usage)
        subtotal, on_solar_energy_amount, off_solar_energy_amount = (
            BillingEngine.compute_ppa_off_grid_subtotal_and_vat_rate(
                on_solar_energy_kwh=on_solar_energy_kwh,
                off_solar_energy_kwh=off_solar_energy_kwh,
                efl_rate_kwh=contract_settings.efl_standard_rate_kwh,
                tariff_indexed_rule_type=tariff_indexed_rule_type,
                active_tariff=active_tariff_slots,
            )
        )
        energy_mix = json.dumps(
            {
                "solar": f"{float(solar_energy_kwh):.2f}",
                "gen": f"{float(gen_energy_kwh):.2f}",
            }
        )

        create_invoice_meter_data: list[BaseInvoiceMeterDataModel] = []
        for device in devices:
            if device.slave_id == load_meter.get("slave_id"):
                create_invoice_meter_data.extend(
                    [
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.SITE_METER_1_DAY.value,
                            period_start_reading=Decimal(period_start_meter[0][0]),
                            period_end_reading=Decimal(period_end_meter[0][0]),
                        ),
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.SITE_METER_1_NIGHT.value,
                            period_start_reading=Decimal(period_start_meter[0][1]),
                            period_end_reading=Decimal(period_end_meter[0][1]),
                        ),
                    ]
                )

            if device.slave_id == gen_meter.get("slave_id"):
                create_invoice_meter_data.extend(
                    [
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.GEN_METER_1_DAY.value,
                            period_start_reading=Decimal(period_start_meter[1][0]),
                            period_end_reading=Decimal(period_end_meter[1][0]),
                        ),
                        BaseInvoiceMeterDataModel(
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.GEN_METER_1_NIGHT.value,
                            period_start_reading=Decimal(period_start_meter[1][1]),
                            period_end_reading=Decimal(period_end_meter[1][1]),
                        ),
                    ]
                )

        create_invoice_line_items = [
            BaseInvoiceLineItemModel(
                description=InvoiceLineItemEnum.ON_SOLAR_ENERGY_SUPPLIED,
                energy_kwh=Decimal(on_solar_energy_kwh),
                tariff_rate=Decimal(active_tariff_slots[0]["rate"]),
                tariff_slot=active_tariff_slots[0]["slot"],
                tariff_period=int(active_tariff_slots[0]["period_number"]),
                amount=Decimal(on_solar_energy_amount),
            ),
            BaseInvoiceLineItemModel(
                description=InvoiceLineItemEnum.OFF_SOLAR_ENERGY_SUPPLIED,
                energy_kwh=Decimal(off_solar_energy_kwh),
                tariff_rate=Decimal(active_tariff_slots[1]["rate"]),
                tariff_slot=active_tariff_slots[1]["slot"],
                tariff_period=int(active_tariff_slots[1]["period_number"]),
                amount=Decimal(off_solar_energy_amount),
            ),
        ]

        invoice_details_dict = InvoiceDetailsDict(
            subtotal=subtotal,
            vat_rate=contract_settings.vat_rate,
            invoice_line_items=create_invoice_line_items,
            invoice_meter_data=create_invoice_meter_data,
            energy_mix=energy_mix,
        )

        return invoice_details_dict

    @staticmethod
    def compute_ppa_off_grid_invoice(
        contract: Contract,
        contract_settings: ContractSettings,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
        is_multi_day: bool = False,
    ):
        active_tariff_slots = contract.details.active_tariff_slots
        readings = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
            is_multi_day=is_multi_day,
        )
        if not readings:
            logger.warning(f"No readings found for gateway {gateway_id}")
            return

        period_start_data, period_end_data = readings

        period_start_meter = BillingEngine.get_ppa_off_grid_meter_data(period_start_data)
        period_end_meter = BillingEngine.get_ppa_off_grid_meter_data(period_end_data)

        usage = BillingEngine.compute_ppa_off_grid_day_night_usage(
            period_start_meter_tariff_reading=period_start_meter,
            period_end_meter_tariff_reading=period_end_meter,
        )
        on_solar_energy_kwh, off_solar_energy_kwh = BillingEngine.compute_ppa_off_grid_line_items(usage=usage)
        solar_energy_kwh, gen_energy_kwh = BillingEngine.compute_ppa_off_grid_energy_mix(usage=usage)
        subtotal, _, _ = BillingEngine.compute_ppa_off_grid_subtotal_and_vat_rate(
            on_solar_energy_kwh=on_solar_energy_kwh,
            off_solar_energy_kwh=off_solar_energy_kwh,
            efl_rate_kwh=contract_settings.efl_standard_rate_kwh,
            tariff_indexed_rule_type=contract.details.tariff_indexed_rule_type,
            active_tariff=active_tariff_slots,
        )
        energy_mix = json.dumps(
            {
                "solar": f"{float(solar_energy_kwh):.2f}",
                "gen": f"{float(gen_energy_kwh):.2f}",
            }
        )

        create_invoice_dict = CreateInvoiceModel(
            period_start_at=period_start,
            period_end_at=period_end,
            period_start_telemetry_data=json.dumps(jsonable_encoder(period_start_data)),
            period_end_telemetry_data=json.dumps(jsonable_encoder(period_end_data)),
            subtotal=subtotal,
            vat_rate=contract_settings.vat_rate,
            efl_standard_rate_kwh=contract_settings.efl_standard_rate_kwh,
            energy_mix=energy_mix,
        ).model_dump()
        create_invoice_dict["contract_uid"] = contract.uid
        create_invoice_dict["invoice_ref"] = InvoiceRepository._build_invoice_ref()
        return (create_invoice_dict, readings)

    @staticmethod
    def compute_ppa_on_grid_no_battery_invoice(
        contract: Contract,
        contract_settings: ContractSettings,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
        is_multi_day: bool = False,
    ):
        tariffs: list[OnGridNoBatteryTariffSlotModel] = json.loads(contract.details.ppa_on_grid_no_battery_tariffs)
        readings = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
            is_multi_day=is_multi_day,
        )
        if not readings:
            logger.warning(f"No readings found for gateway {gateway_id}")
            return None

        period_start_data, period_end_data = readings

        period_start_meters_import_data: OnGridNoBatteryMeterImportData = (
            BillingEngine.get_ppa_on_grid_no_battery_kwh_kvarh_import_data(periodic_energy_data=period_start_data)
        )
        period_end_meters_import_data: OnGridNoBatteryMeterImportData = (
            BillingEngine.get_ppa_on_grid_no_battery_kwh_kvarh_import_data(periodic_energy_data=period_end_data)
        )
        usage: OnGridNoBatteryUsage = BillingEngine.compute_ppa_on_grid_no_battery_usage(
            period_start_meters_import_data=period_start_meters_import_data,
            period_end_meters_import_data=period_end_meters_import_data,
        )
        energy_mix = BillingEngine.compute_ppa_on_grid_no_battery_energy_mix(usage=usage)

        for tariff in tariffs:
            if tariff.get("slot") == OnGridNoBatterySlotEnum.SOLAR.value:
                solar_tariff = tariff
            else:
                grid_tariff = tariff

        subtotal, solar_rate = BillingEngine.compute_ppa_on_grid_no_battery_subtotal(
            solar_meters_import_usage=usage.solar_meters_import_usage,
            tariff_indexed_rule_type=contract.details.tariff_indexed_rule_type,
            efl_standard_rate_kwh=contract_settings.efl_standard_rate_kwh,
            solar_tariff=solar_tariff,
        )

        energy_mix = json.dumps(
            {
                "solar": f"{float(energy_mix.solar):.2f}",
                "grid": f"{float(energy_mix.grid):.2f}",
            }
        )

        create_invoice_dict: CreateInvoiceModel = CreateInvoiceModel(
            period_start_at=period_start,
            period_end_at=period_end,
            period_start_telemetry_data=json.dumps(jsonable_encoder(period_start_data)),
            period_end_telemetry_data=json.dumps(jsonable_encoder(period_end_data)),
            subtotal=subtotal,
            vat_rate=contract_settings.vat_rate,
            efl_standard_rate_kwh=contract_settings.efl_standard_rate_kwh,
            energy_mix=energy_mix,
        ).model_dump()
        create_invoice_dict["contract_uid"] = contract.uid
        create_invoice_dict["invoice_ref"] = InvoiceRepository._build_invoice_ref()

        return ComputePPAOnGridNoBatteryInvoiceResp(
            **{
                "create_invoice_dict": create_invoice_dict,
                "period_start_meters_import_data": period_start_meters_import_data,
                "period_end_meters_import_data": period_end_meters_import_data,
                "usage": usage,
                "solar_tariff": solar_tariff,
                "grid_tariff": grid_tariff,
                "solar_rate": solar_rate,
                "subtotal": subtotal,
            }
        )

    @staticmethod
    def compute_ppa_on_grid_with_battery_invoice(
        contract: Contract,
        contract_settings: ContractSettings,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
    ):
        pass

    @staticmethod
    def compute_invoice_data(
        contract: Contract,
        contract_settings: ContractSettings,
        devices: Device,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
        is_ppa_off_grid: bool,
        is_ppa_on_grid_with_battery: bool,
        is_multi_day: bool = False,
    ):
        """
        Run billing engine computation for a given period.
        Returns:
            (create_invoice_dict, invoice_details_dict) or None.
        """
        create_invoice_dict = None
        invoice_details_dict = None

        if is_ppa_off_grid or is_ppa_on_grid_with_battery:
            off_grid_result = BillingEngine.compute_ppa_off_grid_invoice(
                contract=contract,
                contract_settings=contract_settings,
                gateway_id=gateway_id,
                period_start=period_start,
                period_end=period_end,
                is_multi_day=is_multi_day,
            )
            if off_grid_result is None:
                return None

            create_invoice_dict, readings = off_grid_result
            invoice_details_dict = BillingEngine.build_ppa_off_grid_invoice_details(
                devices=devices,
                contract_settings=contract_settings,
                active_tariff_slots=contract.details.active_tariff_slots,
                tariff_indexed_rule_type=contract.details.tariff_indexed_rule_type,
                readings=readings,
            )
        else:
            computed = BillingEngine.compute_ppa_on_grid_no_battery_invoice(
                contract=contract,
                contract_settings=contract_settings,
                gateway_id=gateway_id,
                period_start=period_start,
                period_end=period_end,
                is_multi_day=is_multi_day,
            )
            if computed is None:
                return None

            create_invoice_dict = computed.create_invoice_dict
            invoice_details_dict = BillingEngine.build_ppa_on_grid_no_battery_invoice_details(
                devices=devices,
                contract_settings=contract_settings,
                computed_ppa_no_battery_invoice_resp=computed,
            )

        if create_invoice_dict is None or invoice_details_dict is None:
            return None

        return create_invoice_dict, invoice_details_dict

    @staticmethod
    def generate_pdf(
        contract: Contract,
        result: tuple[Invoice, list[InvoiceMeterData], list[InvoiceLineItem]],
        contract_settings: ContractSettings,
    ):
        invoice, meter_data, line_items = result

        pdf_bytes = InvoicePDF.render_invoice_pdf(
            invoice=invoice,
            contract=contract,
            line_items=line_items,
            meter_data=meter_data,
            contract_settings=contract_settings,
        )

        key = f"invoices/{invoice.invoice_ref}.pdf"

        return pdf_bytes, key

    @staticmethod
    def store_pdf_in_s3(pdf_bytes: bytes, key: str, invoice_ref: str):
        try:
            S3Service.upload_pdf(key=key, pdf_bytes=pdf_bytes)
        except Exception as e:
            logger.error(f"Failed to upload PDF to S3 for invoice {invoice_ref}: {e}")
            return
