import json
from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.clients.model import Client
from app.modules.contracts.model import Contract, ContractDetails
from app.modules.contracts.schema import (
    CreateContractDetailsModel,
    CreateContractModel,
)
from app.modules.settings.repository import SettingsRepository
from app.modules.sites.model import Site

logger = setup_logger(__name__)


class ContractRepository:
    """Data-access layer for the Contract and ContractDetails models."""

    def __init__(self, session: AsyncSession):
        """Initialise the repository with a database session.

        Args:
            session: An async SQLAlchemy session used for all database operations.
        """
        self.session = session

    def _build_contract_ref(self, name: str):
        """Generate a unique contract reference string from the contract type name.

        Args:
            name: The contract type name (e.g. "PPA" or "Lease") used to derive the prefix.

        Returns:
            A formatted contract reference string such as "PC-2025-AB1C2D".
        """
        prefix = f"{name.upper()[0]}C"
        current_year = str(datetime.now().year)

        return f"{prefix}-{current_year}-{Authentication.generate_otp()}"

    async def get_contract_by_uid(self, contract_uid: UUID):
        """Fetch a contract with its associated client, site, and details by UUID.

        Args:
            contract_uid: The UUID of the contract to retrieve.

        Returns:
            A row tuple of (Contract, Client, Site, ContractDetails), or None if not found.
        """
        statement = (
            select(Contract, Client, Site, ContractDetails)
            .outerjoin(Client, Client.uid == Contract.client_uid)
            .outerjoin(Site, Site.uid == Contract.site_uid)
            .outerjoin(ContractDetails, ContractDetails.contract_uid == Contract.uid)
            .where(Contract.uid == contract_uid)
        )
        result = await self.session.exec(statement)
        row = result.first()

        if not row:
            return None

        return row

    async def get_contract_by_site_uid(self, site_uid: UUID):
        """Fetch a contract with eagerly loaded client, site, and details by site UUID.

        Args:
            site_uid: The UUID of the site whose contract to retrieve.

        Returns:
            The matching Contract ORM instance (with relationships loaded), or None if not found.
        """
        statement = (
            select(Contract)
            .options(
                joinedload(Contract.client),
                joinedload(Contract.site),
                joinedload(Contract.details),
            )
            .where(Contract.site_uid == site_uid)
        )
        result = await self.session.exec(statement=statement)
        contract = result.first()

        return contract

    async def get_contract_uid_by_site_uid(self, site_uid: UUID):
        """Retrieve only the UID of the contract associated with a given site.

        Args:
            site_uid: The UUID of the site to look up.

        Returns:
            The contract UUID, or None if no contract exists for the site.
        """
        statement = select(Contract.uid).where(Contract.site_uid == site_uid)
        result = await self.session.exec(statement)
        return result.first()

    async def get_contract_details_by_uid(self, contract_details_uid: UUID):
        """Fetch contract details with its parent contract eagerly loaded by UUID.

        Args:
            contract_details_uid: The UUID of the ContractDetails record to retrieve.

        Returns:
            The matching ContractDetails ORM instance, or None if not found.
        """
        statement = (
            select(ContractDetails)
            .options(selectinload(ContractDetails.contract))
            .where(ContractDetails.uid == contract_details_uid)
        )
        result = await self.session.exec(statement=statement)
        contract_details = result.first()

        return contract_details

    async def get_contract_with_details_only(self, contract_uid: UUID):
        """Fetch a contract with its details relationship eagerly loaded.

        Args:
            contract_uid: The UUID of the contract to retrieve.

        Returns:
            The matching Contract ORM instance with details loaded, or None if not found.
        """
        statement = select(Contract).options(selectinload(Contract.details)).where(Contract.uid == contract_uid)
        result = await self.session.exec(statement)
        return result.first()

    async def get_contract_details_with_contract(self, contract_details_uid: UUID):
        """Fetch contract details with the parent contract's type and system_mode loaded.

        Args:
            contract_details_uid: The UUID of the ContractDetails record to retrieve.

        Returns:
            The matching ContractDetails ORM instance with selective contract fields loaded, or None.
        """
        statement = (
            select(ContractDetails)
            .options(
                selectinload(ContractDetails.contract).load_only(
                    Contract.contract_type,
                    Contract.system_mode,
                )
            )
            .where(ContractDetails.uid == contract_details_uid)
        )
        result = await self.session.exec(statement)
        return result.first()

    async def create_contract(self, user_uid: UUID, data: CreateContractModel):
        """Create and persist a new contract record.

        Args:
            user_uid: The UUID of the admin user creating the contract.
            data: The validated model containing contract creation fields.

        Returns:
            The newly created Contract ORM instance, or None if an error occurs.
        """
        data_dict = data.model_dump()
        data_dict["user_uid"] = user_uid
        data_dict["contract_ref"] = self._build_contract_ref(name=data.contract_type)
        new_contract = Contract(**data_dict)

        try:
            self.session.add(new_contract)
            await self.session.commit()

            return new_contract
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating contract: {e}")

    async def create_contract_details(self, contract_uid: UUID, data: CreateContractDetailsModel):
        """Create and persist contract details for a given contract.

        Serialises tariff slots to JSON before saving when tariff_periods and tariffs are both provided.

        Args:
            contract_uid: The UUID of the parent contract.
            data: The validated model containing contract detail fields.

        Returns:
            The newly created ContractDetails ORM instance.

        Raises:
            Exception: Re-raises any database or serialisation error after rolling back.
        """
        try:
            data_dict = data.model_dump(exclude_none=True)
            settings_repo = SettingsRepository(session=self.session)
            current_rate = await settings_repo.get_current_rate()

            if current_rate:
                data_dict.__setattr__("efl_standard_rate_kwh", current_rate.efl_standard_rate_kwh)
            if data.tariffs and data.tariff_periods:
                data_dict.pop("tariffs", None)

                tariffs_as_dicts = [t.model_dump() for t in data.tariffs]
                data_dict["tariff_slots"] = json.dumps(tariffs_as_dicts)

            data_dict["contract_uid"] = contract_uid
            contract_details = ContractDetails(**data_dict)
            self.session.add(contract_details)
            await self.session.commit()

            return contract_details
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to create contract details: {e}")
            raise

    async def update_contract_details(self, contract_details: ContractDetails, data: CreateContractDetailsModel):
        """Apply an update to existing contract details, serialising tariff slots when provided.

        Args:
            contract_details: The ContractDetails ORM instance to update.
            data: The validated model containing updated field values (None values are skipped).

        Returns:
            None

        Raises:
            ValueError: If a value assignment fails validation.
            Exception: Re-raises any other database error after rolling back.
        """
        try:
            data_dict = data.model_dump(exclude_none=True)
            data_dict.pop("contract_uid", None)

            if not data_dict:
                return "No changes to update"

            for field, value in data_dict.items():
                if field == "tariff_periods":
                    setattr(contract_details, "tariff_periods", value)
                elif field == "tariffs" and value is not None:
                    setattr(
                        contract_details,
                        "tariff_slots",
                        json.dumps(value),
                    )
                else:
                    setattr(contract_details, field, value)

            await self.session.commit()
            await self.session.refresh(contract_details)
        except ValueError as e:
            await self.session.rollback()
            logger.error(f"Error updating contract details: {e}")
            raise
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating contract details: {e}")
            raise


def get_contract_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a ContractRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A ContractRepository bound to the provided session.
    """
    return ContractRepository(session=session)
