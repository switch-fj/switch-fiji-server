import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from matplotlib.dates import relativedelta

from app.core.logger import setup_logger
from app.modules.clients.schema import ClientPortfolioMetrics
from app.modules.contracts.model import Contract
from app.modules.devices.model import Device
from app.modules.invoices.repository import InvoiceRepository
from app.modules.settings.repository import SettingsRepository
from app.modules.sites.model import Site
from app.modules.sites.schema import (
    SiteHealth,
    SitePortfolioMetrics,
    SiteSummaryMetrics,
    SiteTrendMetrics,
)
from app.utils.date import clamp_day_to_month
from app.utils.wizard import (
    extract_production_kwh,
    extract_total_consumption_kwh,
    get_expected_production_kwh,
    get_wizard_class_for_contract,
)

logger = setup_logger(__name__)


class PortfolioMetricsService:
    def __init__(self, invoice_repo: InvoiceRepository, settings_repo: SettingsRepository):
        self.invoice_repo = invoice_repo
        self.settings_repo = settings_repo

    async def compute_site_metrics(
        self,
        site: Site,
        contract: Contract,
        devices: list[Device],
        now: datetime,
    ):
        tz = ZoneInfo(site.tz or contract.timezone)
        local_now = now.astimezone(tz)

        month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        last_month_end = month_start - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        same_day_last_month = datetime.combine(
            clamp_day_to_month(last_month_start.year, last_month_start.month, local_now.day),
            local_now.time(),
            tzinfo=tz,
        )

        metrics = SitePortfolioMetrics(site_uid=site.uid, billing_frequency=contract.details.billing_frequency)

        try:
            mtd_wizard = await self.build_wizard_for_period(
                contract=contract,
                devices=devices,
                period_start=month_start,
                period_end=local_now,
            )
            if mtd_wizard:
                energy_mix = mtd_wizard.energy_mix
                metrics.production_mtd_kwh = extract_production_kwh(energy_mix)
                production = metrics.production_mtd_kwh
                consumption = extract_total_consumption_kwh(energy_mix)
                metrics.coverage_numerator_kwh = production
                metrics.coverage_denominator_kwh = consumption

                target_pct = contract.details.target_coverage_pct or 0.0
                if production is not None and consumption:
                    metrics.coverage_actual_pct = production / consumption
                else:
                    metrics.coverage_actual_pct = 0.0
                metrics.coverage_target_pct = target_pct

            compare_wizard = await self.build_wizard_for_period(
                contract=contract,
                devices=devices,
                period_start=last_month_start,
                period_end=same_day_last_month,
            )
            if compare_wizard:
                metrics.last_month_production_kwh = extract_production_kwh(compare_wizard.energy_mix)

            if site.pv_degradation and site.pv_summary:
                metrics.trend_vs_plan = await self.compute_trend_metrics(
                    site=site, contract=contract, devices=devices, now=now
                )

            metrics.total_bill_from_inception = await self.invoice_repo.get_billed_lifetime(
                contract_uid=contract.uid, up_to=now
            )

        except Exception as exc:
            logger.warning(f"Portfolio metrics failed for site {site.uid}: {exc}")

        return metrics

    async def compute_trend_metrics(
        self,
        site: Site,
        contract: Contract,
        devices: list[Device],
        now: datetime,
    ) -> SiteTrendMetrics:
        tz = ZoneInfo(site.tz or contract.timezone)
        local_now = now.astimezone(tz)
        current_month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        ratios = []
        for i in range(1, 7):
            month_start = current_month_start - relativedelta(months=i)
            month_end = month_start + relativedelta(months=1) - timedelta(seconds=1)

            expected = get_expected_production_kwh(
                site.pv_degradation, month_start.date(), site.pv_summary.commissioned_at
            )
            wizard = await self.build_wizard_for_period(contract, devices, month_start, month_end)
            if expected is None or wizard is None:
                ratios.append(None)
                continue

            actual = extract_production_kwh(wizard.energy_mix)
            ratios.append((actual - expected) / expected if actual is not None else None)

        def avg(subset: list[Optional[float]]) -> Optional[float]:
            if any(r is None for r in subset):
                return None
            return round(sum(subset) / len(subset), 2)

        return SiteTrendMetrics(
            trend_3mo_pct=avg(ratios[:3]),
            trend_6mo_pct=avg(ratios[:6]),
        )

    async def build_wizard_for_period(
        self,
        contract: Contract,
        devices: list[Device],
        period_start: datetime,
        period_end: datetime,
    ):
        wizard_cls = get_wizard_class_for_contract(contract)
        if wizard_cls is None:
            return None

        start_snapshot = await self.invoice_repo.get_nearest_snapshot(contract_uid=contract.uid, target=period_start)
        end_snapshot = await self.invoice_repo.get_nearest_snapshot(contract_uid=contract.uid, target=period_end)

        if start_snapshot is None or end_snapshot is None:
            return None

        contract_settings = await self.settings_repo.get_contract_settings()

        return wizard_cls.factory(
            telemetry_start_reading=json.loads(start_snapshot.period_end_telemetry_data),
            telemetry_end_reading=json.loads(end_snapshot.period_end_telemetry_data),
            contract=contract,
            devices=devices,
            contract_settings=contract_settings,
        )

    async def aggregate_client_metrics(self, site_metrics: list[SitePortfolioMetrics], contracts: list[Contract]):
        production_mtd = sum(m.production_mtd_kwh or 0 for m in site_metrics)
        production_compare = sum(m.last_month_production_kwh or 0 for m in site_metrics)
        billed = sum(
            (m.total_bill_from_inception or Decimal(0) for m in site_metrics),
            Decimal(0),
        )

        coverage_num = sum(m.coverage_numerator_kwh or 0 for m in site_metrics)
        coverage_denom = sum(m.coverage_denominator_kwh or 0 for m in site_metrics)
        coverage_actual = (coverage_num / coverage_denom) if coverage_denom else 0.0

        targets = [c.details.target_coverage_pct for c in contracts if c.details.target_coverage_pct is not None]
        coverage_target = sum(targets) / len(targets) if targets else None

        return ClientPortfolioMetrics(
            production_mtd_kwh=production_mtd,
            last_month_production_kwh=production_compare,
            coverage_actual_pct=coverage_actual,
            coverage_target_pct=coverage_target,
            total_bill_from_inception=billed,
        )

    @staticmethod
    def site_summary_metrics(site_health: SiteHealth, site_metrics: list[SitePortfolioMetrics]):
        production_mtd_kwh = sum(m.production_mtd_kwh or 0 for m in site_metrics)
        last_month_production_kwh = sum(m.last_month_production_kwh or 0 for m in site_metrics)
        total_bill_from_inception = sum(
            (m.total_bill_from_inception or Decimal(0) for m in site_metrics),
            Decimal(0),
        )

        return SiteSummaryMetrics(
            production_mtd_kwh=production_mtd_kwh,
            last_month_production_kwh=last_month_production_kwh,
            total_bill_from_inception=total_bill_from_inception,
            site_health=site_health,
        )
