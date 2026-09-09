import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import selectinload
from sqlmodel import desc, func, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.device.schema import DeviceModel
from app.core.config import Config
from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.database.redis import async_redis_client
from app.modules.billing.engine import BillingEngine
from app.modules.clients.model import Client
from app.modules.contracts.model import Contract
from app.modules.contracts.schema import ContractRespModel
from app.modules.devices.model import Device
from app.modules.invoices.model import (
    Invoice,
    InvoiceSnapshot,
)
from app.modules.sites.model import Site, SiteEnergyUsage
from app.modules.sites.schema import (
    CreateSiteModel,
    SiteDailyStatsRespModel,
    SiteData,
    SiteDetailedRespModel,
    SiteHealth,
    SitePortfolioMetrics,
    SiteRespModel,
    SiteRespWithMetrics,
    UpdateSiteModel,
)
from app.services.portfolio_metrics import PortfolioMetricsService
from app.shared.constants import Constants
from app.shared.schema import CursorPaginationModel, PaginatedRespModel
from app.utils.pagination import Pagination

logger = setup_logger(__name__)


class SiteRepository:
    """Data-access layer for the Site model with Redis cache integration."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    async def sites_count(self):
        result = await self.session.exec(select(func.count(Site.uid)).where(Site.deleted_at.is_(None)))
        return result.one()

    async def get_client_exists(self, client_uid: UUID) -> bool:
        """Check whether a client exists, using a short-lived Redis cache to avoid repeated DB lookups.

        Args:
            client_uid: The UUID of the client to check.

        Returns:
            True if the client exists in the database, False otherwise.
        """
        cache_key = f"client:exists:{client_uid}"
        cached = await async_redis_client.client.get(cache_key)

        if cached:
            return True

        client = await self.session.get(Client, client_uid)
        if client:
            await async_redis_client.client.set(cache_key, "1", ex=300)

        return client is not None

    async def get_sites_by_client_uid(self, client_uid: UUID):
        """Retrieve all active sites for a client, returning a cached response when available.

        Args:
            client_uid: The UUID of the client whose sites to retrieve.

        Returns:
            A list of SiteRespModel instances, or None if the client does not exist.
        """
        cached = await async_redis_client.get_client_sites(str(client_uid))
        if cached:
            return [SiteRespModel.model_validate(item) for item in json.loads(cached)]

        relevant_sites_subq = (
            select(Site.uid).where(Site.client_uid == client_uid).where(Site.deleted_at.is_(None)).subquery()
        )

        device_count_subq = (
            select(Device.site_uid, func.count(Device.id).label("device_count"))
            .where(Device.site_uid.in_(select(relevant_sites_subq)))
            .group_by(Device.site_uid)
            .subquery()
        )

        statement = (
            select(
                Site,
                Contract,
                func.coalesce(device_count_subq.c.device_count, 0).label("device_count"),
            )
            .outerjoin(Contract, Contract.site_uid == Site.uid)
            .outerjoin(device_count_subq, device_count_subq.c.site_uid == Site.uid)
            .where(Site.client_uid == client_uid)
            .where(Site.deleted_at.is_(None))
            .order_by(Site.created_at.desc())
        )

        result = await self.session.exec(statement)
        rows = result.all()

        if not rows:
            client_exists = await self.session.get(Client, client_uid)
            if not client_exists:
                return None

        sites = [
            SiteRespModel.model_validate(
                {
                    **row.Site.__dict__,
                    "device_count": row.device_count,
                    "contract": row.Contract,
                }
            )
            for row in rows
        ]

        await async_redis_client.set_client_sites(
            data=json.dumps([s.model_dump(mode="json") for s in sites]),
            client_uid=str(client_uid),
        )

        return sites

    async def get_sites_by_client_uid_v2(self, client_uid: UUID, portfolio_metrics: PortfolioMetricsService):
        """Retrieve all active sites for a client, with metrics, cached for 1hr.

        Args:
            client_uid: The UUID of the client whose sites to retrieve.
            portfolio_metrics: Service used to compute per-site portfolio metrics.

        Returns:
            A list of SiteRespWithMetrics instances, or None if the client does not exist.
        """
        cache_key = Constants.CLIENT_SITE_METRICS.replace(":client_uid", str(client_uid))
        cached = await async_redis_client.client.get(cache_key)
        if cached:
            return [SiteRespWithMetrics.model_validate(item) for item in json.loads(cached)]

        statement = (
            select(Site)
            .options(
                selectinload(Site.contract).selectinload(Contract.details),
                selectinload(Site.devices),
            )
            .where(Site.client_uid == client_uid, Site.deleted_at.is_(None))
            .order_by(Site.created_at.desc())
        )

        result = await self.session.exec(statement)
        sites = result.all()

        if not sites:
            client_exists = await self.session.get(Client, client_uid)
            if not client_exists:
                return None
            return []

        now = datetime.now(timezone.utc)
        site_resp_models: list[SiteRespWithMetrics] = []

        for site in sites:
            devices = site.devices
            contract = site.contract
            metrics = SitePortfolioMetrics()

            if contract is not None and contract.details is not None:
                metrics = await portfolio_metrics.compute_site_metrics(
                    site=site, contract=contract, devices=devices, now=now
                )

            site_resp_models.append(
                SiteRespWithMetrics(
                    site=SiteData.model_validate(site),
                    devices=[DeviceModel.model_validate(device) for device in devices],
                    contract=(ContractRespModel.model_validate(contract) if contract else None),
                    metrics=metrics,
                )
            )

        await async_redis_client.client.set(
            cache_key,
            json.dumps([s.model_dump(mode="json") for s in site_resp_models]),
            ex=3600,
        )

        return site_resp_models

    async def get_sites(
        self,
        portfolio_metrics: PortfolioMetricsService,
        q: Optional[str] = None,
        limit: int = Config.DEFAULT_PAGE_LIMIT,
        next_cursor: Optional[str] = None,
        prev_cursor: Optional[str] = None,
        _is_all_sites: bool = False,
    ):
        """Retrieve a cursor-paginated list of all sites across every client, with metrics.

        Args:
            portfolio_metrics: Service used to compute per-site portfolio metrics.
            q: Optional search string matched against site name and site_id.
            limit: Maximum number of records to return per page.
            next_cursor: Encrypted cursor pointing to the next page.
            prev_cursor: Encrypted cursor pointing to the previous page.

        Returns:
            A PaginatedRespModel containing SiteRespWithMetrics items and pagination metadata.
        """
        statement = (
            select(Site)
            .options(
                selectinload(Site.contract).selectinload(Contract.details),
                selectinload(Site.devices),
            )
            .where(Site.deleted_at.is_(None))
            .order_by(Site.created_at.desc())
        )

        if next_cursor:
            statement = statement.where(Site.id < Pagination.decrypt_cursor(next_cursor))

        if prev_cursor:
            statement = statement.where(Site.id > Pagination.decrypt_cursor(prev_cursor))

        if q:
            search = f"%{q}%"
            statement = statement.where(Site.site_name.ilike(search) | Site.site_id.ilike(search))

        statement = statement.limit(limit + 1)

        result = await self.session.exec(statement)
        sites = result.all()

        has_more = len(sites) > limit
        items = sites if _is_all_sites else sites[:limit]

        now = datetime.now(timezone.utc)
        site_resp_models: list[SiteRespWithMetrics] = []

        for site in items:
            devices = site.devices
            contract = site.contract
            metrics = SitePortfolioMetrics()

            if contract is not None and contract.details is not None:
                metrics = await portfolio_metrics.compute_site_metrics(
                    site=site, contract=contract, devices=devices, now=now
                )

            site_resp_models.append(
                SiteRespWithMetrics(
                    site=SiteData.model_validate(site),
                    devices=[DeviceModel.model_validate(device) for device in devices],
                    contract=(ContractRespModel.model_validate(contract) if contract else None),
                    metrics=metrics,
                )
            )

        next_cursor_out = None
        prev_cursor_out = None

        if items:
            prev_cursor_out = Pagination.encrypt_cursor(items[0].id)

        if has_more:
            next_cursor_out = Pagination.encrypt_cursor(items[-1].id)

        return PaginatedRespModel.model_validate(
            {
                "items": site_resp_models,
                "pagination": CursorPaginationModel(
                    limit=limit,
                    next_cursor=next_cursor_out,
                    prev_cursor=prev_cursor_out,
                ),
            }
        )

    async def get_site_by_uid(self, site_uid: UUID):
        """Fetch a site by its primary UUID.

        Args:
            site_uid: The UUID of the site to retrieve.

        Returns:
            The matching Site ORM instance, or None if not found.
        """
        statement = select(Site).options(selectinload(Site.contract)).where(Site.uid == site_uid)
        result = await self.session.exec(statement=statement)
        site = result.first()

        return site

    async def get_detailed_sites_by_client_uid(self, client_uid: UUID):
        """Retrieve all sites for a client with their client, contract, and contract details eagerly loaded.

        Args:
            client_uid: The UUID of the client whose sites to retrieve.

        Returns:
            A list of SiteDetailedRespModel instances.
        """
        statement = (
            select(Site)
            .options(
                selectinload(Site.client),
                selectinload(Site.contract),
                selectinload(Site.contract.details),
            )
            .where(Site.client_uid == client_uid)
        )
        result = await self.session.exec(statement=statement)
        sites = result.all()

        return [SiteDetailedRespModel.model_validate(site) for site in sites]

    async def create_site(
        self,
        data: CreateSiteModel,
    ):
        """Create and persist a new site record, then invalidate the client's sites cache.

        Args:
            data: The validated model containing site creation fields.

        Returns:
            The newly created Site ORM instance, or None if an error occurs.
        """
        data_dict = data.model_dump()
        new_site = Site(**data_dict)

        try:
            self.session.add(new_site)
            await self.session.commit()
            await self.session.refresh(new_site)
            await async_redis_client.invalidate_client_sites_cache(str(data.client_uid))

            return new_site
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating site {e}")

    async def update_site(self, site: Site, data: UpdateSiteModel):
        """Apply an update to an existing site record and invalidate the client's sites cache.

        Args:
            site: The Site ORM instance to update.
            data: The validated model containing fields to update (None values are skipped).

        Returns:
            The updated Site ORM instance.
        """
        data_dict = data.model_dump(exclude_none=True)

        for key, value in data_dict.items():
            setattr(site, key, value)

        await self.session.commit()
        await self.session.refresh(site)
        await async_redis_client.invalidate_client_sites_cache(str(site.client_uid))
        return site

    async def compute_site_stats(self, site_uid: UUID):
        """Compute live site stats from DB only — no DynamoDB or Celery needed.

        Args:
            site_uid: The UUID of the site to compute stats for.

        Returns:
            A dict of stats, or None if the site has no active contract.
        """

        contract_result = await self.session.exec(
            select(Contract).options(selectinload(Contract.details)).where(Contract.site_uid == site_uid)
        )
        contract = contract_result.one_or_none()

        site_uid_str = str(site_uid)
        performance_vs_baseline_pct = 0.0
        expected_generation_kwh = 0.0
        actual_generation_kwh = 0.0
        projected_generation_kwh = 0.0
        projected_invoice_value = 0.0
        billing_period_progress_pct = 0.0
        contract_progress_pct = 0.0
        mtd_generation_kwh = 0.0
        last_invoice_date = None
        last_invoice_amount = None

        if not contract or not contract.details:
            return SiteDailyStatsRespModel.model_validate(
                {
                    "site_uid": site_uid_str,
                    "expected_generation_kwh": expected_generation_kwh,
                    "actual_generation_kwh": actual_generation_kwh,
                    "mtd_generation_kwh": mtd_generation_kwh,
                    "projected_generation_kwh": projected_generation_kwh,
                    "projected_invoice_value": projected_invoice_value,
                    "billing_period_progress_pct": billing_period_progress_pct,
                    "contract_progress_pct": contract_progress_pct,
                    "performance_vs_baseline_pct": performance_vs_baseline_pct,
                    "last_invoice_date": last_invoice_date,
                    "last_invoice_amount": last_invoice_amount,
                }
            )

        now = datetime.now(tz=timezone.utc)

        commissioned_at = contract.details.actual_commissioned_at or contract.details.commissioned_at
        end_at = contract.details.actual_end_at or contract.details.end_at

        period_start, period_end = BillingEngine.get_current_billing_period(
            commissioned_at=commissioned_at,
            billing_frequency=contract.details.billing_frequency,
            as_of=now,
        )

        period_total_secs = (period_end - period_start).total_seconds()
        period_elapsed_secs = (now - period_start).total_seconds()
        billing_period_progress_pct = round(max(0.0, min((period_elapsed_secs / period_total_secs) * 100, 100.0)), 2)

        contract_total_secs = (end_at - commissioned_at).total_seconds()
        contract_elapsed_secs = (now - commissioned_at).total_seconds()
        contract_progress_pct = round(max(0.0, min((contract_elapsed_secs / contract_total_secs) * 100, 100.0)), 2)

        days_in_period = (period_end - period_start).days or 1
        days_elapsed_in_period = min((now - period_start).days, days_in_period)
        expected_generation_kwh = round(
            (contract.details.system_size_kwp or 0)
            * (contract.details.guaranteed_production_kwh_per_kwp or 0)
            * (days_elapsed_in_period / 365),
            2,
        )

        result = await self.session.exec(
            select(InvoiceSnapshot)
            .options(selectinload(InvoiceSnapshot.meter_data))
            .where(
                InvoiceSnapshot.contract_uid == contract.uid,
                InvoiceSnapshot.period_start_at == period_start,
            )
            .order_by(desc(InvoiceSnapshot.snapshotted_at))
            .limit(1)
        )
        latest_snapshot = result.one_or_none()

        if latest_snapshot and latest_snapshot.meter_data:
            actual_generation_kwh = round(float(sum(m.usage for m in latest_snapshot.meter_data)), 2)
            if billing_period_progress_pct > 0:
                projected_generation_kwh = round(actual_generation_kwh / (billing_period_progress_pct / 100), 2)
                projected_invoice_value = round(
                    projected_generation_kwh * float(latest_snapshot.efl_standard_rate_kwh),
                    2,
                )

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mtd_snapshots_result = await self.session.exec(
            select(InvoiceSnapshot)
            .options(selectinload(InvoiceSnapshot.meter_data))
            .where(
                InvoiceSnapshot.contract_uid == contract.uid,
                InvoiceSnapshot.period_start_at >= month_start,
            )
        )
        mtd_snapshots = mtd_snapshots_result.fetchall()

        mtd_generation_kwh = round(
            float(sum(float(m.usage) for snapshot in mtd_snapshots for m in snapshot.meter_data)),
            2,
        )

        full_period_baseline_kwh = (contract.details.guaranteed_production_kwh_per_kwp or 0) * (
            contract.details.system_size_kwp or 0
        )

        baseline_kwh = round(full_period_baseline_kwh * (billing_period_progress_pct / 100), 2)

        if baseline_kwh > 0:
            performance_vs_baseline_pct = round(
                (actual_generation_kwh - baseline_kwh) / baseline_kwh * 100,
                2,
            )

        last_invoice_result = await self.session.exec(
            select(Invoice).where(Invoice.contract_uid == contract.uid).order_by(desc(Invoice.period_end_at)).limit(1)
        )
        last_invoice = last_invoice_result.one_or_none()
        last_invoice_date = last_invoice.period_end_at.isoformat() if last_invoice else None
        last_invoice_amount = float(last_invoice.total) if last_invoice else None

        return SiteDailyStatsRespModel.model_validate(
            {
                "site_uid": site_uid_str,
                "expected_generation_kwh": expected_generation_kwh,
                "actual_generation_kwh": actual_generation_kwh,
                "mtd_generation_kwh": mtd_generation_kwh,
                "projected_generation_kwh": projected_generation_kwh,
                "projected_invoice_value": projected_invoice_value,
                "billing_period_progress_pct": billing_period_progress_pct,
                "contract_progress_pct": contract_progress_pct,
                "performance_vs_baseline_pct": performance_vs_baseline_pct,
                "last_invoice_date": last_invoice_date,
                "last_invoice_amount": last_invoice_amount,
            }
        )

    async def engineers_get_details_by_client_uid(self, client_uid: UUID):
        result = await self.session.exec(
            select(Site)
            .options(selectinload(Site.devices))
            .where(Site.client_uid == client_uid, Site.deleted_at.is_(None))
            .order_by(Site.created_at.desc())
        )
        sites = result.all()

        return sites

    async def get_healthy_sites(self) -> list[Site]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = await self.session.exec(
            select(Site)
            .join(Device, Device.site_uid == Site.uid)
            .where(Site.deleted_at.is_(None))
            .group_by(Site.uid)
            .having(func.min(Device.last_seen_at) >= cutoff)
        )

        sites = result.all()
        return sites

    async def get_faulty_sites(self) -> list[Site]:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = await self.session.exec(
            select(Site)
            .join(Device, Device.site_uid == Site.uid)
            .where(Site.deleted_at.is_(None))
            .group_by(Site.uid)
            .having(func.min(Device.last_seen_at) < cutoff)
        )

        sites = result.all()
        return sites

    async def site_health_counts(self):
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)

        site_min_last_seen = (
            select(
                Device.site_uid,
                func.min(Device.last_seen_at).label("min_last_seen"),
                func.bool_or(Device.last_seen_at.is_(None)).label("has_never_reported"),
            )
            .group_by(Device.site_uid)
            .subquery()
        )

        result = await self.session.exec(
            select(
                func.count().label("total"),
                func.count().filter(site_min_last_seen.c.site_uid.is_(None)).label("unprovisioned"),
                func.count()
                .filter(
                    site_min_last_seen.c.min_last_seen >= cutoff,
                    site_min_last_seen.c.has_never_reported.is_(False),
                )
                .label("healthy"),
                func.count()
                .filter(
                    site_min_last_seen.c.site_uid.is_not(None),
                    or_(
                        site_min_last_seen.c.min_last_seen < cutoff,
                        site_min_last_seen.c.has_never_reported.is_(True),
                    ),
                )
                .label("faulty"),
            )
            .select_from(Site)
            .outerjoin(site_min_last_seen, site_min_last_seen.c.site_uid == Site.uid)
            .where(Site.deleted_at.is_(None))
        )

        summary = result.one()
        return SiteHealth.model_validate(
            {
                "healthy": summary.healthy,
                "faulty": summary.faulty,
                "unprovisioned": summary.unprovisioned,
                "total": summary.total,
            }
        )

    async def site_health_by_client_uid(self, client_uid: UUID):
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)

        site_min_last_seen = (
            select(
                Device.site_uid,
                func.min(Device.last_seen_at).label("min_last_seen"),
                func.bool_or(Device.last_seen_at.is_(None)).label("has_never_reported"),
            )
            .group_by(Device.site_uid)
            .subquery()
        )

        result = await self.session.exec(
            select(
                func.count().label("total"),
                func.count().filter(site_min_last_seen.c.site_uid.is_(None)).label("unprovisioned"),
                func.count()
                .filter(
                    site_min_last_seen.c.min_last_seen >= cutoff,
                    site_min_last_seen.c.has_never_reported.is_(False),
                )
                .label("healthy"),
                func.count()
                .filter(
                    site_min_last_seen.c.site_uid.is_not(None),
                    or_(
                        site_min_last_seen.c.min_last_seen < cutoff,
                        site_min_last_seen.c.has_never_reported.is_(True),
                    ),
                )
                .label("faulty"),
            )
            .select_from(Site)
            .outerjoin(site_min_last_seen, site_min_last_seen.c.site_uid == Site.uid)
            .where(Site.client_uid == client_uid, Site.deleted_at.is_(None))
        )

        summary = result.one()
        return SiteHealth.model_validate(
            {
                "healthy": summary.healthy,
                "faulty": summary.faulty,
                "unprovisioned": summary.unprovisioned,
                "total": summary.total,
            }
        )


def get_site_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a SiteRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A SiteRepository bound to the provided session.
    """
    return SiteRepository(session=session)


class SiteEnergyUsageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_usage(self, site_uid: UUID, date_at: date):
        result = await self.session.exec(
            select(SiteEnergyUsage).where(
                SiteEnergyUsage.site_uid == site_uid,
                SiteEnergyUsage.deleted_at.is_(None),
                SiteEnergyUsage.date_at == date_at,
            )
        )
        site_energy_usage = result.one_or_none()

        return site_energy_usage

    async def create(self, site_uid: UUID, date_at: date):
        site_energy_usage = SiteEnergyUsage(
            site_uid=site_uid,
            date_at=date_at,
            interval_in_minutes=30,
            is_completed=False,
        )
        self.session.add(site_energy_usage)
        await self.session.commit()

        return site_energy_usage


def get_site_energy_usage_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a SiteEnergyUsageRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A SiteEnergyUsageRepository bound to the provided session.
    """
    return SiteEnergyUsageRepository(session=session)
