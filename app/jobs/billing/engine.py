import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from app.core.logger import setup_logger
from app.database.celery import celery_dynamo_client
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import (
    ContractBillingFrequencyEnum,
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
    CreateInvoiceLineItemModel,
    CreateInvoiceMeterDataModel,
    CreateInvoiceModel,
    InvoiceDetailsDict,
    InvoiceLineItemEnum,
    InvoiceMeterLabelEnum,
)
from app.modules.settings.model import ContractSettings
from app.services.s3 import S3Service

logger = setup_logger(__name__)


class BillingEngine:
    @staticmethod
    def _extract_meter_by_description(reading: dict, description: str) -> dict | None:
        for meter in reading.get("meters", []):
            if meter.get("description") == description:
                return meter
        return None

    @staticmethod
    def get_current_billing_period(
        timezone_key: str,
        commissioned_at: datetime,
        billing_frequency: str,
        as_of: datetime,
    ):
        tz = ZoneInfo(timezone_key)

        try:
            freq = ContractBillingFrequencyEnum(billing_frequency.lower())
        except ValueError:
            raise ValueError(f"Unsupported billing frequency: {billing_frequency}")

        diff = relativedelta(as_of, commissioned_at.astimezone(tz=tz))
        match freq:
            # case ContractBillingFrequencyEnum.WEEKLY:
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
            load_meter.get("tariff", 0)["kwh_t1"],
            load_meter.get("tariff", 0)["kwh_t2"],
        ]
        gen_meter_tariff = [
            gen_meter.get("tariff", 0)["kwh_t1"],
            gen_meter.get("tariff", 0)["kwh_t2"],
        ]

        return (
            site_meter_tariff,
            gen_meter_tariff,
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
    def compute_ppa_off_grid_energy_mix(usage: dict[str, Any]):

        solar_energy_kwh = usage.get("site_meter_day_usage", 0) + usage.get("site_meter_night_usage", 0)
        gen_energy_kwh = usage.get("gen_meter_day_usage", 0) + usage.get("gen_meter_night_usage", 0)

        return (solar_energy_kwh, gen_energy_kwh)

    @staticmethod
    def compute_ppa_off_grid_subtotal_and_vat_rate(
        on_solar_energy_kwh,
        off_solar_energy_kwh,
        efl_rate_kwh: Decimal,
        vat_rate: int,
        active_tariff: list[dict],
    ):
        efl_rate_kwh = int(efl_rate_kwh)
        on_solar_energy_kwh = float(on_solar_energy_kwh)
        off_solar_energy_kwh = float(off_solar_energy_kwh)

        day_tariff = active_tariff[0]
        night_tariff = active_tariff[1]

        if day_tariff["slot_type"] == TariffSlotTypeEnum.FIXED:
            day_rate = float(day_tariff["rate"])
        else:
            tariff_rate = float(day_tariff["rate"])
            day_rate = 100 - tariff_rate if tariff_rate < 0 else 100 + tariff_rate
            day_rate = round(efl_rate_kwh * (day_rate / 100), 2)

        if night_tariff["slot_type"] == TariffSlotTypeEnum.FIXED:
            night_rate = float(night_tariff["rate"])
        else:
            tariff_rate = float(night_tariff["rate"])
            night_rate = 100 - tariff_rate if tariff_rate < 0 else 100 + tariff_rate
            night_rate = round(efl_rate_kwh * (night_rate / 100), 2)

        on_solar_energy_amount = on_solar_energy_kwh * day_rate
        off_solar_energy_amount = off_solar_energy_kwh * night_rate

        subtotal = on_solar_energy_amount + off_solar_energy_amount

        return (subtotal, vat_rate, on_solar_energy_amount, off_solar_energy_amount)

    @staticmethod
    def build_invoice_details(
        devices: list[Device],
        contract_settings: ContractSettings,
        active_tariff_slots: list[dict],
        readings: tuple[dict, dict],
        new_invoice: Invoice,
    ):
        period_start_data, period_end_data = readings

        period_start_meter = BillingEngine.get_ppa_off_grid_meter_data(period_start_data)
        period_end_meter = BillingEngine.get_ppa_off_grid_meter_data(period_end_data)

        load_meter = BillingEngine._extract_meter_by_description(period_start_data, MeterRoleEnum.LOAD_METER)
        gen_meter = BillingEngine._extract_meter_by_description(period_start_data, MeterRoleEnum.GEN_METER)

        usage = BillingEngine.compute_ppa_off_grid_day_night_usage(
            period_start_meter_tariff_reading=period_start_meter,
            period_end_meter_tariff_reading=period_end_meter,
        )
        on_solar_energy_kwh, off_solar_energy_kwh = BillingEngine.compute_ppa_off_grid_line_items(usage=usage)
        solar_energy_kwh, gen_energy_kwh = BillingEngine.compute_ppa_off_grid_energy_mix(usage=usage)
        subtotal, vat_rate, on_solar_energy_amount, off_solar_energy_amount = (
            BillingEngine.compute_ppa_off_grid_subtotal_and_vat_rate(
                on_solar_energy_kwh=on_solar_energy_kwh,
                off_solar_energy_kwh=off_solar_energy_kwh,
                efl_rate_kwh=contract_settings.efl_standard_rate_kwh,
                vat_rate=contract_settings.vat_rate,
                active_tariff=active_tariff_slots,
            )
        )
        energy_mix = json.dumps({"solar": float(solar_energy_kwh), "gen": float(gen_energy_kwh)})

        create_invoice_meter_data: list[CreateInvoiceMeterDataModel] = []
        for device in devices:
            if device.slave_id == load_meter.get("slave_id"):
                create_invoice_meter_data.extend(
                    [
                        CreateInvoiceMeterDataModel(
                            invoice_uid=new_invoice.uid,
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.SITE_METER_1_DAY.value,
                            period_start_reading=Decimal(period_start_meter[0][0]),
                            period_end_reading=Decimal(period_end_meter[0][0]),
                        ),
                        CreateInvoiceMeterDataModel(
                            invoice_uid=new_invoice.uid,
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
                        CreateInvoiceMeterDataModel(
                            invoice_uid=new_invoice.uid,
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.GEN_METER_1_DAY.value,
                            period_start_reading=Decimal(period_start_meter[1][0]),
                            period_end_reading=Decimal(period_end_meter[1][0]),
                        ),
                        CreateInvoiceMeterDataModel(
                            invoice_uid=new_invoice.uid,
                            device_uid=device.uid,
                            label=InvoiceMeterLabelEnum.GEN_METER_1_NIGHT.value,
                            period_start_reading=Decimal(period_start_meter[1][1]),
                            period_end_reading=Decimal(period_end_meter[1][1]),
                        ),
                    ]
                )

        create_invoice_line_items = [
            CreateInvoiceLineItemModel(
                invoice_uid=new_invoice.uid,
                description=InvoiceLineItemEnum.ON_SOLAR_ENERGY_SUPPLIED,
                energy_kwh=Decimal(on_solar_energy_kwh),
                tariff_rate=Decimal(active_tariff_slots[0]["rate"]),
                tariff_slot=active_tariff_slots[0]["slot"],
                tariff_period=int(active_tariff_slots[0]["period_number"]),
                amount=Decimal(on_solar_energy_amount),
            ),
            CreateInvoiceLineItemModel(
                invoice_uid=new_invoice.uid,
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
            vat_rate=vat_rate,
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
    ):
        active_tariff_slots = contract.details.active_tariff_slots
        readings = celery_dynamo_client.get_readings_for_billing_period(
            gateway_id=gateway_id,
            period_start=period_start,
            period_end=period_end,
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
        subtotal, vat_rate, _, _ = BillingEngine.compute_ppa_off_grid_subtotal_and_vat_rate(
            on_solar_energy_kwh=on_solar_energy_kwh,
            off_solar_energy_kwh=off_solar_energy_kwh,
            efl_rate_kwh=contract_settings.efl_standard_rate_kwh,
            vat_rate=contract_settings.vat_rate,
            active_tariff=active_tariff_slots,
        )
        energy_mix = json.dumps({"solar": float(solar_energy_kwh), "gen": float(gen_energy_kwh)})

        create_invoice_dict = CreateInvoiceModel(
            period_start_at=period_start,
            period_end_at=period_end,
            subtotal=subtotal,
            vat_rate=vat_rate,
            energy_mix=energy_mix,
        ).model_dump()
        create_invoice_dict["contract_uid"] = contract.uid
        create_invoice_dict["invoice_ref"] = InvoiceRepository._build_invoice_ref()

        return (create_invoice_dict, readings)

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
