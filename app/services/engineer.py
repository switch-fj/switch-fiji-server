from fastapi import Depends
from sqlalchemy.ext.asyncio.session import AsyncSession

from app.api.v1.engineer.schema import ResourceStatsModel
from app.database.postgres import get_session
from app.modules.clients.repository import ClientRepository
from app.modules.devices.device_repository import DeviceRepository
from app.modules.sites.repository import SiteRepository


class EngineeringService:
    def __init__(self, session: AsyncSession):
        self.site_repo = SiteRepository(session=session)
        self.device_repo = DeviceRepository(session=session)
        self.client_repo = ClientRepository(session=session)

    async def stat(self):
        devices_count = await self.device_repo.devices_count()
        sites_count = await self.site_repo.sites_count()
        clients_count = await self.client_repo.clients_count()

        return ResourceStatsModel(clients=clients_count, sites=sites_count, devices=devices_count)


def get_engr_service(
    session: AsyncSession = Depends(get_session),
):
    return EngineeringService(session=session)
