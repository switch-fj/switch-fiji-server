from uuid import UUID

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.devices.device_repository import DeviceRepository


class DeviceService:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.device_repo = DeviceRepository(session=session)

    async def get_devices_by_site(self, site_uid: UUID):
        devices = await self.device_repo.get_devices_by_site(site_uid=site_uid)

        return devices


def get_device_service(
    session: AsyncSession = Depends(get_session),
):
    return DeviceService(session=session)
