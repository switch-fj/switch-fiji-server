from datetime import date, datetime, time, timezone
from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database.postgres import get_session
from app.modules.batteries_soc.model import (
    BatterySOCConfigHistory,
    BatteryStateofCharge,
)
from app.modules.batteries_soc.schema import (
    ConfigBatterySOCInputModel,
)


class BatterySOCRepository:
    """Data-access layer for BatteryStateofCharge configuration"""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    async def get_config_by_site(self, site_uid: UUID):
        statement = select(BatterySOCConfigHistory).where(BatterySOCConfigHistory.site_uid == site_uid)
        result = await self.session.exec(statement)
        battery_soc_config_history = result.first()

        return battery_soc_config_history

    async def get_site_current_config(self, site_uid: UUID):
        statement = select(BatterySOCConfigHistory).where(
            BatterySOCConfigHistory.site_uid == site_uid,
            BatterySOCConfigHistory.effective_to.is_(None),
        )
        result = await self.session.exec(statement)
        return result.first()

    async def get_battery_soc_by_date(self, site_uid: UUID, date_at: date):
        statement = select(BatteryStateofCharge).where(
            BatteryStateofCharge.site_uid == site_uid,
            BatteryStateofCharge.date_at == date_at,
        )
        result = await self.session.exec(statement)
        battery_soc = result.one_or_none()

        return battery_soc

    async def config_battery_soc_input(
        self,
        site_uid: UUID,
        user_uid: UUID,
        battery_soc_input: ConfigBatterySOCInputModel,
    ):
        now = datetime.now(tz=timezone.utc)
        current_config = await self.get_site_current_config(site_uid=site_uid)
        if current_config:
            current_config.effective_to = now
            self.session.add(current_config)

        battery_soc_config_history = BatterySOCConfigHistory(
            site_uid=site_uid,
            user_uid=user_uid,
            config_input_str=battery_soc_input.model_dump_json(),
            effective_from=now,
        )
        self.session.add(battery_soc_config_history)
        await self.session.commit()

        return battery_soc_config_history

    async def create_battery_soc(self, site_uid: UUID, battery_soc_config_history_uid: UUID, date_at: date):
        battery_state_of_charge = BatteryStateofCharge(
            site_uid=site_uid,
            battery_soc_config_uid=battery_soc_config_history_uid,
            date_at=date_at,
            from_=time(9, 0),
            to=time(15, 0),
            interval_in_minutes=30,
            is_completed=False,
        )

        self.session.add(battery_state_of_charge)
        await self.session.commit()

        return battery_state_of_charge


def get_battery_soc_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a BatterySOCRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A BatterySOCRepository bound to the provided session.
    """
    return BatterySOCRepository(session=session)
