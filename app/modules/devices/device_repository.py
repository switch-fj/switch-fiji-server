from fastapi import Depends
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.devices.model import Device


class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def devices_count(self):
        result = await self.session.exec(select(func.count(Device.uid)).where(Device.deleted_at.is_(None)))

        return result.one()


def get_invoice_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides an DeviceRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        An DeviceRepository bound to the provided session.
    """
    return DeviceRepository(session=session)
