import json
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import selectinload
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.database.redis import async_redis_client
from app.modules.clients.model import Client
from app.modules.contracts.model import Contract
from app.modules.devices.model import Device
from app.modules.sites.model import Site
from app.modules.sites.schema import (
    CreateSiteModel,
    SiteDetailedRespModel,
    SiteRespModel,
    UpdateSiteModel,
)

logger = setup_logger(__name__)


class SiteRepository:
    """Data-access layer for the Site model with Redis cache integration."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

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

        result = await self.session.execute(statement)
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

    async def get_site_by_uid(self, site_uid: UUID):
        """Fetch a site by its primary UUID.

        Args:
            site_uid: The UUID of the site to retrieve.

        Returns:
            The matching Site ORM instance, or None if not found.
        """
        statement = select(Site).where(Site.uid == site_uid)
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
        """Apply a partial update to an existing site record and invalidate the client's sites cache.

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


def get_site_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a SiteRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A SiteRepository bound to the provided session.
    """
    return SiteRepository(session=session)
