from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.sites.model import Site
from app.modules.sites.schema import SiteDetailedRespModel, SiteRespModel


class SiteRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_sites_by_client_uid(self, client_uid: UUID):
        statement = select(Site).where(Site.client_uid == client_uid)
        result = await self.session.exec(statement=statement)
        sites = result.all()

        return [SiteRespModel.model_validate(site) for site in sites]

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


def get_site_repo(session: AsyncSession = Depends(get_session)):
    return SiteRepository(session=session)
