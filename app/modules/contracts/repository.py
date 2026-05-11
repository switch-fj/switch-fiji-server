import json
from calendar import monthrange
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.clients.model import Client
from app.modules.contracts.model import Contract, ContractDetails
from app.modules.contracts.schema import (
    CreateContractDetailsModel,
    CreateContractModel,
    EnergyPortfolioRespModel,
)
from app.modules.invoices.model import InvoiceSnapshot, InvoiceSnapshotMeterData
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
            current_rate = await settings_repo.get_current_efl_rate()

            data_dict.pop("tariffs", None)

            if current_rate:
                data_dict["efl_standard_rate_kwh"] = current_rate.efl_standard_rate_kwh
            if data.tariff_periods:
                if data.tariffs:
                    tariffs_as_dicts = [t.model_dump() for t in data.tariffs]
                    data_dict["tariff_slots"] = json.dumps(tariffs_as_dicts)

                if data.ppa_on_grid_no_battery_tariffs:
                    ppa_on_grid_no_battery_tariffs_as_dicts = [
                        t.model_dump() for t in data.ppa_on_grid_no_battery_tariffs
                    ]
                    data_dict["ppa_on_grid_no_battery_tariffs"] = json.dumps(ppa_on_grid_no_battery_tariffs_as_dicts)

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
                elif field == "ppa_on_grid_no_battery_tariffs" and value is not None:
                    setattr(
                        contract_details,
                        "ppa_on_grid_no_battery_tariffs",
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

    async def compute_energy_portfolio(self):
        """Fetch a contract with its associated client, site, and details by UUID.

        Returns:
            energy portfolio
        """
        now = datetime.now(tz=timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        days_in_month = monthrange(now.year, now.month)[1]
        month_progress = now.day / days_in_month

        baseline_stmt = (
            select(
                func.coalesce(
                    func.sum(
                        ContractDetails.guaranteed_production_kwh_per_kwp
                        * ContractDetails.system_size_kwp
                        * month_progress
                    ),
                    0,
                ).label("baseline_kwh")
            )
            .where(ContractDetails.actual_commissioned_at.isnot(None))
            .where(
                func.now()
                > func.coalesce(
                    ContractDetails.actual_commissioned_at,
                    ContractDetails.commissioned_at,
                )
            )
            .where(func.now() < func.coalesce(ContractDetails.actual_end_at, ContractDetails.end_at))
        )

        baseline_result = await self.session.exec(baseline_stmt)
        baseline_row = baseline_result.one()

        invoice_stmt = (
            select(
                func.coalesce(
                    func.sum(
                        InvoiceSnapshotMeterData.period_end_reading - InvoiceSnapshotMeterData.period_start_reading
                    ),
                    0,
                ).label("produced_kwh"),
                func.coalesce(func.sum(InvoiceSnapshot.total), 0).label("invoice_total"),
                func.count(InvoiceSnapshot.uid).label("invoice_count"),
            )
            .select_from(InvoiceSnapshot)
            .join(
                InvoiceSnapshotMeterData,
                InvoiceSnapshotMeterData.snapshot_uid == InvoiceSnapshot.uid,
            )
            .where(InvoiceSnapshot.period_start_at >= month_start)
        )

        invoice_result = await self.session.exec(invoice_stmt)
        invoice_stat = invoice_result.one()

        energy_portfolio_resp = EnergyPortfolioRespModel(
            **{
                "produced_kwh": float(invoice_stat.produced_kwh),
                "baseline_kwh": float(baseline_row.baseline_kwh),
                "invoice_total": float(invoice_stat.invoice_total),
                "invoice_count": invoice_stat.invoice_count,
            }
        )
        return energy_portfolio_resp


def get_contract_repo(session: AsyncSession = Depends(get_session)):
    """FastAPI dependency that provides a ContractRepository instance.

    Args:
        session: Injected async database session from get_session.

    Returns:
        A ContractRepository bound to the provided session.
    """
    return ContractRepository(session=session)
