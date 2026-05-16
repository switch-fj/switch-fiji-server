import calendar
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from app.modules.contracts.model import Contract
from app.modules.contracts.wizard.ppa_off_grid import PPAOffGridContractWizard
from app.modules.contracts.wizard.ppa_on_grid_no_battery import (
    PPAOnGridNoBatteryContractWizard,
)
from app.modules.contracts.wizard.ppa_on_grid_with_battery import (
    PPAOnGridWithBatteryContractWizard,
)
from app.modules.devices.model import Device
from app.modules.invoices.model import Invoice
from app.modules.settings.model import ContractSettings
from app.utils.contracts import (
    is_lease,
    is_ppa_off_grid,
    is_ppa_on_grid_no_battery,
    is_ppa_on_grid_with_battery,
)


class SiteStatsWizard:
    def __init__(
        self,
        contract: Contract,
        last_invoice: Optional[Invoice],
        devices: list[Device],
        contract_settings: ContractSettings,
    ):
        self.contract = contract
        self.last_invoice = last_invoice
        self.devices = devices
        self.contract_settings = contract_settings

        self.tz = ZoneInfo(contract.timezone)
        self.now = datetime.now(tz=self.tz)
        self.end_at = contract.details.actual_end_at or contract.details.end_at
        self.commissioned_at = contract.details.actual_commissioned_at or contract.details.commissioned_at

    def billing_period_progress_percentage(self, period_start: datetime, period_end: datetime):
        period_total_secs = (period_end - period_start).total_seconds()
        period_elapsed_secs = (self.now - period_start).total_seconds()
        return round(max(0.0, min((period_elapsed_secs / period_total_secs) * 100, 100.0)), 2)

    def contract_progress_percentage(self):
        contract_total_secs = (self.end_at - self.commissioned_at).total_seconds()
        contract_elapsed_secs = (self.now - self.commissioned_at).total_seconds()
        return round(max(0.0, min((contract_elapsed_secs / contract_total_secs) * 100, 100.0)), 2)

    def expected_generation_for_period_kwh(self, period_start: datetime, period_end: datetime) -> float:
        days_in_period = (period_end - period_start).days or 1
        return round(
            (self.contract.details.system_size_kwp or 0)
            * (self.contract.details.guaranteed_production_kwh_per_kwp or 0)
            * (days_in_period / 365),
            2,
        )

    def expected_generation_remaining_in_period_kwh(self, period_end: datetime) -> float:
        if self.now >= period_end:
            return 0.0
        days_remaining = (period_end - self.now).days
        return round(
            (self.contract.details.system_size_kwp or 0)
            * (self.contract.details.guaranteed_production_kwh_per_kwp or 0)
            * (days_remaining / 365),
            2,
        )

    def actual_generation_kwh_for_reading(self, telemetry_start_reading: dict, telemetry_end_reading: dict):
        generated_energy_kwh = 0
        if not telemetry_start_reading or not telemetry_end_reading:
            return generated_energy_kwh

        if is_lease(contract=self.contract):
            return generated_energy_kwh

        if is_ppa_off_grid(contract=self.contract):
            ppa_off_grid_wizard = PPAOffGridContractWizard.factory(
                telemetry_start_reading=telemetry_start_reading,
                telemetry_end_reading=telemetry_end_reading,
                contract=self.contract,
                devices=self.devices,
                contract_settings=self.contract_settings,
            )

            generated_energy_kwh = ppa_off_grid_wizard.energy_mix.backup_gen + ppa_off_grid_wizard.energy_mix.load

        if is_ppa_on_grid_no_battery(contract=self.contract):
            ppa_on_grid_no_battery_wizard = PPAOnGridNoBatteryContractWizard.factory(
                telemetry_start_reading=telemetry_start_reading,
                telemetry_end_reading=telemetry_end_reading,
                contract=self.contract,
                devices=self.devices,
                contract_settings=self.contract_settings,
            )
            generated_energy_kwh = ppa_on_grid_no_battery_wizard.energy_mix.solar

        if is_ppa_on_grid_with_battery(contract=self.contract):
            ppa_on_grid_with_battery_wizard = PPAOnGridWithBatteryContractWizard.factory(
                telemetry_start_reading=telemetry_start_reading,
                telemetry_end_reading=telemetry_end_reading,
                contract=self.contract,
                devices=self.devices,
                contract_settings=self.contract_settings,
            )
            generated_energy_kwh = (
                ppa_on_grid_with_battery_wizard.energy_mix.battery + ppa_on_grid_with_battery_wizard.energy_mix.solar
            )

        return generated_energy_kwh

    def hybrid_projected_generation_kwh(
        self,
        actual_generation_kwh_for_reading: float,
        period_end: datetime,
    ):
        expected_remaining_kwh = self.expected_generation_remaining_in_period_kwh(period_end)
        projected_hybrid = actual_generation_kwh_for_reading + expected_remaining_kwh
        return round(projected_hybrid, 2)

    def linear_projected_generation_kwh(
        self,
        actual_generation_kwh_for_reading: float,
    ):
        year = self.now.year
        month = self.now.month
        _, total_days_in_month = calendar.monthrange(year, month)

        days_elapsed = self.now.day
        if days_elapsed == 0:
            days_elapsed = 1

        # Method Linear Runway
        daily_average_actual = actual_generation_kwh_for_reading / days_elapsed
        projected_linear = daily_average_actual * total_days_in_month

        return round(projected_linear, 2)

    @property
    def baseline_kwh(self):
        return (self.contract.details.guaranteed_production_kwh_per_kwp or 0) * (
            self.contract.details.system_size_kwp or 0
        )

    def performance_vs_baseline_percentage(self, actual_generation_kwh: float, baseline_kwh: float):
        if not baseline_kwh:
            return 0.0
        return round(
            (actual_generation_kwh - baseline_kwh) / baseline_kwh * 100,
            2,
        )

    def expected_generation_mtd_kwh(self, period_start: datetime, period_end: datetime) -> float:
        """
        Calculates the expected contractual baseline up to the current day.
        """
        days_in_period = (period_end - period_start).days or 1
        days_elapsed_in_period = max(0, min((self.now - period_start).days, days_in_period))

        return round(
            (self.contract.details.system_size_kwp or 0)
            * (self.contract.details.guaranteed_production_kwh_per_kwp or 0)
            * (days_elapsed_in_period / 365),
            2,
        )

    def projected_invoice_value(self, projected_generation_kwh: float) -> float:
        """
        Calculates the estimated financial invoice value for the month by
        applying active tariffs, minimum consumption floors, and minimum spends.
        """
        details = self.contract.details
        if not details:
            return 0.0

        current_rate = float(self.contract_settings.efl_standard_rate_kwh)

        if (
            details.minimum_consumption_monthly_kwh
            and projected_generation_kwh < details.minimum_consumption_monthly_kwh
        ):
            billable_projected_kwh = details.minimum_consumption_monthly_kwh
        else:
            billable_projected_kwh = projected_generation_kwh

        projected_charge = billable_projected_kwh * current_rate

        if details.minimum_spend and projected_charge < details.minimum_spend:
            final_invoice_total = details.minimum_spend
        else:
            final_invoice_total = projected_charge

        return round(final_invoice_total, 2)

    def performance_vs_mtd_expected_percentage(
        self, actual_generation_kwh: float, period_start: datetime, period_end: datetime
    ) -> float:
        mtd_target = self.expected_generation_mtd_kwh(period_start, period_end)
        if not mtd_target:
            return 0.0

        return round((actual_generation_kwh / mtd_target) * 100, 2)

    @property
    def last_invoice_date(self):
        return self.last_invoice.period_end_at.isoformat() if self.last_invoice else None

    @property
    def last_invoice_amount(self):
        return float(self.last_invoice.total) if self.last_invoice else None
