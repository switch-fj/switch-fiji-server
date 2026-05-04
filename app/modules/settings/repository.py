from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.settings.model import (
    ContractEFLRateHistory,
    ContractSettings,
    ContractVATRateHistory,
)
from app.modules.settings.schema import (
    CreateContractEFLRateModel,
    CreateContractVATRateModel,
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
        statement = select(ContractSettings).options(
            selectinload(ContractSettings.efl_rate_history),
            selectinload(ContractSettings.vat_rate_history),
        )
        result = await self.session.exec(statement)
        contract_settings = result.first()

        return contract_settings

    async def create_contract_settings(self) -> ContractSettings:
        new_contract_settings = ContractSettings(
            primary_currency=CurrencyEnum.FJD.value,
            asset_performance=False,
            invoice_emailed=True,
            invoice_generated=False,
        )

        self.session.add(new_contract_settings)
        await self.session.commit()

        await self.create_efl_rate(
            contract_settings_uid=new_contract_settings.uid,
            data=CreateContractEFLRateModel(
                efl_standard_rate_kwh=Decimal("0.49").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                effective_from=datetime.now(),
            ),
        )
        await self.create_vat_rate(
            contract_settings_uid=new_contract_settings.uid,
            data=CreateContractVATRateModel(
                vat_rate=15,
                effective_from=datetime.now(),
            ),
        )

        return await self.get_contract_settings()

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
            if key in ["efl_standard_rate_kwh", "vat_rate"]:
                if key == "vat_rate":
                    await self.create_vat_rate(
                        user_uid=user_uid,
                        data=CreateContractVATRateModel(vat_rate=value, effective_from=datetime.now()),
                    )
                else:
                    await self.create_efl_rate(
                        user_uid=user_uid,
                        data=CreateContractEFLRateModel(efl_standard_rate_kwh=value, effective_from=datetime.now()),
                    )

            else:
                setattr(contract_settings, key, value)

        setattr(contract_settings, "updated_by_uid", user_uid)
        self.session.add(contract_settings)
        await self.session.commit()
        await self.session.refresh(contract_settings)

        return True

    async def get_current_efl_rate(self) -> ContractEFLRateHistory | None:
        """Retrieve the currently active efl rate (where effective_to is NULL).

        Returns:
            The active ContractEFLRateHistory ORM instance, or None if not found.
        """
        statement = select(ContractEFLRateHistory).where(ContractEFLRateHistory.effective_to.is_(None))
        result = await self.session.exec(statement)
        return result.first()

    async def get_efl_rate_history(self) -> list[ContractEFLRateHistory]:
        """Retrieve all efl rate history entries for a ContractSettings record, newest first.

        Returns:
            A list of ContractEFLRateHistory ORM instances.
        """
        statement = select(ContractEFLRateHistory).order_by(ContractEFLRateHistory.effective_from.desc())
        result = await self.session.exec(statement)
        return result.all()

    async def create_efl_rate(
        self,
        data: CreateContractEFLRateModel,
        contract_settings_uid: Optional[UUID] = None,
        user_uid: Optional[UUID] = None,
    ) -> ContractEFLRateHistory:
        """Close off the current active efl rate and insert a new efl rate history entry.

        Args:
            contract_settings_uid: optional contract settings uid,
            user_uid: optional UUID of the user creating the new rate.
            data: The validated model containing the new efl rate and effective_from date.

        Returns:
            The newly created ContractVATRateHistory ORM instance.
        """
        current_rate = await self.get_current_efl_rate()
        if current_rate:
            current_rate.effective_to = data.effective_from
            self.session.add(current_rate)

        if not contract_settings_uid:
            settings = await self.get_contract_settings()
            contract_settings_uid = settings.uid

        new_rate = ContractEFLRateHistory(
            contract_settings_uid=contract_settings_uid,
            efl_standard_rate_kwh=data.efl_standard_rate_kwh.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            effective_from=data.effective_from,
            effective_to=None,
            created_by_uid=user_uid,
        )

        self.session.add(new_rate)
        await self.session.commit()
        await self.session.refresh(new_rate)

        return new_rate

    async def get_current_vat_rate(self) -> ContractVATRateHistory | None:
        """Retrieve the currently active efl rate (where effective_to is NULL).

        Returns:
            The active ContractVATRateHistory ORM instance, or None if not found.
        """
        statement = select(ContractVATRateHistory).where(ContractVATRateHistory.effective_to.is_(None))
        result = await self.session.exec(statement)
        return result.first()

    async def get_vat_rate_history(self) -> list[ContractVATRateHistory]:
        """Retrieve all vat rate history entries for a ContractSettings record, newest first.

        Returns:
            A list of ContractVATRateHistory ORM instances.
        """
        statement = select(ContractVATRateHistory).order_by(ContractVATRateHistory.effective_from.desc())
        result = await self.session.exec(statement)
        return result.all()

    async def create_vat_rate(
        self,
        data: CreateContractVATRateModel,
        contract_settings_uid: Optional[UUID] = None,
        user_uid: Optional[UUID] = None,
    ) -> ContractEFLRateHistory:
        """Close off the current active efl rate and insert a new efl rate history entry.

        Args:
            contract_settings_uid: optional contract settings uid,
            user_uid: The UUID of the user creating the new rate.
            data: The validated model containing the new efl rate and effective_from date.

        Returns:
            The newly created ContractVATRateHistory ORM instance.
        """
        # close off the current active efl rate
        current_rate = await self.get_current_vat_rate()
        if current_rate:
            current_rate.effective_to = data.effective_from
            self.session.add(current_rate)

        if not contract_settings_uid:
            settings = await self.get_contract_settings()
            contract_settings_uid = settings.uid

        new_rate = ContractVATRateHistory(
            contract_settings_uid=contract_settings_uid,
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
