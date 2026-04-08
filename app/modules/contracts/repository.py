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
from app.modules.contracts.model import Contract, ContractDetails
from app.modules.contracts.schema import (
    CreateContractDetailsModel,
    CreateContractModel,
)

logger = setup_logger(__name__)


class ContractRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _build_contract_ref(self, name: str):
        prefix = f"{name.upper()[0]}C"
        current_year = str(datetime.now().year)

        return f"{prefix}-{current_year}-{Authentication.generate_otp()}"

    async def get_contract_by_uid(self, contract_uid: UUID):
        statement = (
            select(Contract)
            .options(
                selectinload(Contract.client),
                selectinload(Contract.site),
                selectinload(Contract.details),
            )
            .where(Contract.uid == contract_uid)
        )
        result = await self.session.exec(statement=statement)
        contract = result.first()

        return contract

    async def get_contract_by_site_uid(self, site_uid: UUID):
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

    async def get_contract_details_by_uid(self, contract_details_uid: UUID):
        statement = (
            select(ContractDetails)
            .options(selectinload(ContractDetails.contract))
            .where(ContractDetails.uid == contract_details_uid)
        )
        result = await self.session.exec(statement=statement)
        contract_details = result.first()

        return contract_details

    async def create_contract(self, user_uid: UUID, data: CreateContractModel):
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
        try:
            data_dict = data.model_dump(exclude_none=True)
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
        try:
            data_dict = data.model_dump(exclude_none=True)
            data_dict.pop("contract_uid", None)

            if not data_dict:
                return "No changes to update"

            for field, value in data_dict.items():
                if field == "tariff_periods":
                    setattr(contract_details, "tariff_periods", value)
                elif field == "tariffs":
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
    return ContractRepository(session=session)
