from decimal import Decimal
from uuid import UUID

from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.settings.model import ContractSettings
from app.modules.settings.schema import UpdateContractSettingsModel
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

    async def get_contract_settings(self):
        """Retrieve the single ContractSettings record.

        Returns:
            The ContractSettings ORM instance, or None if no record exists.
        """
        statement = select(ContractSettings)
        result = await self.session.exec(statement)
        contract_settings = result.first()

        return contract_settings

    async def create_contract_settings(self):
        """Create and persist the default ContractSettings record.

        Returns:
            The newly created ContractSettings ORM instance.
        """
        new_contract_settings = ContractSettings(
            **{
                "vat_rate": 15,
                "efl_standard_rate_kwh": Decimal("0.32"),
                "primary_currency": CurrencyEnum.USD.value,
                "asset_performance": False,
                "invoice_emailed": True,
                "invoice_generated": False,
            }
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
    ):
        """Apply partial updates to the ContractSettings record and persist them.

        Args:
            user_uid: The UUID of the user performing the update, recorded as updated_by_uid.
            contract_settings: The existing ContractSettings ORM instance to update.
            data: The validated model containing fields to update (None fields are skipped).

        Returns:
            True once the update has been committed successfully.
        """
        data_dict = data.model_dump(exclude_none=True)

        if len(list(data_dict.keys())) == 0:
            return True

        for key, value in data_dict.items():
            setattr(contract_settings, key, value)

        setattr(contract_settings, "updated_by_uid", user_uid)
        self.session.add(contract_settings)
        await self.session.commit()
        await self.session.refresh(contract_settings)

        return True


def get_settings_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a SettingsRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A SettingsRepository bound to the provided session.
    """
    return SettingsRepository(session=session)
