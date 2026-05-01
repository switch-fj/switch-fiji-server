from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.settings.model import ContractSettings, ContractSettingsRateHistory
from app.modules.settings.schema import (
    CreateContractSettingsRateModel,
    UpdateContractSettingsModel,
)
from app.shared.schema import CurrencyEnum

logger = setup_logger(__name__)


class SettingsRepository:
    """Data-access layer for ContractSettings configuration."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    async def get_contract_settings(self) -> ContractSettings | None:
        """Retrieve the single ContractSettings record.

        Returns:
            The ContractSettings ORM instance, or None if no record exists.
        """
        statement = select(ContractSettings)
        result = await self.session.exec(statement)
        contract_settings = result.first()

        return contract_settings

    async def create_contract_settings(self) -> ContractSettings:
        """Create and persist the default ContractSettings record.

        Returns:
            The newly created ContractSettings ORM instance.
        """
        new_contract_settings = ContractSettings(
            primary_currency=CurrencyEnum.FJD.value,
            asset_performance=False,
            invoice_emailed=True,
            invoice_generated=False,
        )

        self.session.add(new_contract_settings)
        await self.session.commit()
        await self.session.refresh(new_contract_settings)

        return new_contract_settings

    async def update_contract_settings(
        self,
        user_uid: UUID,
        contract_settings: ContractSettings,
        data: UpdateContractSettingsModel,
    ) -> bool:
        """Apply partial updates to the ContractSettings record and persist them.

        Args:
            user_uid: The UUID of the user performing the update, recorded as updated_by_uid.
            contract_settings: The existing ContractSettings ORM instance to update.
            data: The validated model containing fields to update (None fields are skipped).

        Returns:
            True once the update has been committed successfully.
        """
        data_dict = data.model_dump(exclude_none=True)

        if not data_dict:
            return True

        for key, value in data_dict.items():
            setattr(contract_settings, key, value)

        setattr(contract_settings, "updated_by_uid", user_uid)
        self.session.add(contract_settings)
        await self.session.commit()
        await self.session.refresh(contract_settings)

        return True

    async def get_current_rate(self) -> ContractSettingsRateHistory | None:
        """Retrieve the currently active rate (where effective_to is NULL).

        Returns:
            The active ContractSettingsRateHistory ORM instance, or None if not found.
        """
        statement = select(ContractSettingsRateHistory).where(ContractSettingsRateHistory.effective_to.is_(None))
        result = await self.session.exec(statement)
        return result.first()

    async def get_rate_history(self, contract_settings_uid: UUID) -> list[ContractSettingsRateHistory]:
        """Retrieve all rate history entries for a ContractSettings record, newest first.

        Args:
            contract_settings_uid: The UUID of the ContractSettings record.

        Returns:
            A list of ContractSettingsRateHistory ORM instances.
        """
        statement = (
            select(ContractSettingsRateHistory)
            .where(ContractSettingsRateHistory.contract_settings_uid == contract_settings_uid)
            .order_by(ContractSettingsRateHistory.effective_from.desc())
        )
        result = await self.session.exec(statement)
        return result.all()

    async def create_rate(
        self,
        contract_settings_uid: UUID,
        user_uid: UUID,
        data: CreateContractSettingsRateModel,
    ) -> ContractSettingsRateHistory:
        """Close off the current active rate and insert a new rate history entry.

        Args:
            contract_settings_uid: The UUID of the ContractSettings record.
            user_uid: The UUID of the user creating the new rate.
            data: The validated model containing the new rate and effective_from date.

        Returns:
            The newly created ContractSettingsRateHistory ORM instance.
        """
        # close off the current active rate
        current_rate = await self.get_current_rate()
        if current_rate:
            current_rate.effective_to = data.effective_from
            self.session.add(current_rate)

        new_rate = ContractSettingsRateHistory(
            contract_settings_uid=contract_settings_uid,
            efl_standard_rate_kwh=data.efl_standard_rate_kwh,
            vat_rate=data.vat_rate,
            effective_from=data.effective_from,
            effective_to=None,
            created_by_uid=user_uid,
        )

        self.session.add(new_rate)
        await self.session.commit()
        await self.session.refresh(new_rate)

        return new_rate


def get_settings_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a SettingsRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A SettingsRepository bound to the provided session.
    """
    return SettingsRepository(session=session)
