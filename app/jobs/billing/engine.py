from datetime import datetime, timezone
from typing import Any

from dateutil.relativedelta import relativedelta

from app.core.logger import setup_logger
from app.modules.contracts.schema import (
    ContractBillingFrequencyEnum,
    TariffSlotTypeEnum,
)
from app.modules.devices.schema import MeterRoleEnum

logger = setup_logger(__name__)


class Billing:
    @staticmethod
    def _extract_meter_by_description(reading: dict, description: str) -> dict | None:
        for meter in reading.get("meters", []):
            if meter.get("description") == description:
                return meter
        return None

    @staticmethod
    def get_current_billing_period(
        commissioned_at: datetime,
        billing_frequency: str,
        as_of: datetime = None,
    ):
        if as_of is None:
            as_of = datetime.now(timezone.utc)

        try:
            freq = ContractBillingFrequencyEnum(billing_frequency.lower())
        except ValueError:
            raise ValueError(f"Unsupported billing frequency: {billing_frequency}")

        diff = relativedelta(as_of, commissioned_at)
        match freq:
            case ContractBillingFrequencyEnum.WEEKLY:
                total_seconds = (as_of - commissioned_at).total_seconds()
                n = int(total_seconds // (5 * 60))
                delta = relativedelta(minutes=5)
            # case ContractBillingFrequencyEnum.WEEKLY:
            #     total_days = (as_of - commissioned_at).days
            #     n = total_days // 7
            #     delta = relativedelta(weeks=1)
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

        return period_start, period_end

    @staticmethod
    def get_ppa_off_grid_meter_data(
        periodic_energy_data: dict | Any,
    ):
        load_meter = Billing._extract_meter_by_description(periodic_energy_data, description=MeterRoleEnum.LOAD_METER)
        gen_meter = Billing._extract_meter_by_description(periodic_energy_data, description=MeterRoleEnum.GEN_METER)

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
            "gen_meter_night_usgae": gen_meter_night_usage,
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
        efl_rate_kwh: int,
        active_tariff: list[dict],
    ):
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
        vat_rate = 0.125

        return (subtotal, vat_rate, on_solar_energy_amount, off_solar_energy_amount)
