from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.clients.model import Client
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
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_sites_by_client_uid(self, client_uid: UUID):
        client_exists = await self.session.get(Client, client_uid)
        if not client_exists:
            return None

        device_count_subq = (
            select(Device.site_uid, func.count(Device.id).label("device_count")).group_by(Device.site_uid).subquery()
        )

        statement = (
            select(
                Site,
                func.coalesce(device_count_subq.c.device_count, 0).label("device_count"),
            )
            .outerjoin(device_count_subq, device_count_subq.c.site_uid == Site.uid)
            .options(joinedload(Site.contract))
            .where(Site.client_uid == client_uid)
            .order_by(Site.created_at.desc())
        )

        result = await self.session.execute(statement)
        rows = result.all()

        return [SiteRespModel.model_validate({**row.Site.__dict__, "device_count": row.device_count}) for row in rows]

    async def get_site_by_uid(self, site_uid: UUID):
        statement = select(Site).where(Site.uid == site_uid)
        result = await self.session.exec(statement=statement)
        site = result.first()

        return site

    async def get_detailed_sites_by_client_uid(self, client_uid: UUID):
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
        data_dict = data.model_dump()
        new_site = Site(**data_dict)

        try:
            self.session.add(new_site)
            await self.session.commit()
            await self.session.refresh(new_site)

            return new_site
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating site {e}")

    async def update_site(self, site: Site, data: UpdateSiteModel):
        data_dict = data.model_dump(exclude_none=True)

        for key, value in data_dict.items():
            setattr(site, key, value)

        await self.session.commit()
        await self.session.refresh(site)
        return site


def get_site_repo(session: AsyncSession = Depends(get_session)):
    return SiteRepository(session=session)
