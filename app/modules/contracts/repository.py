from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlmodel import update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.exceptions import BadRequest
from app.database.postgres import get_session
from app.modules.contracts.model import Contract, Tariff
from app.modules.contracts.schema import CreateContractDetailsModel, CreateContractModel


class ContractRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def build_contract_ref(name: str):
        prefix = f"{name.upper()[0]}C"
        current_year = str(datetime.now().year)

        return f"{prefix}-{current_year}-{Authentication.generate_otp(4)}"

    async def create_contract(self, user_uid: UUID, data: CreateContractModel):
        data_dict = data.model_dump()
        data_dict["user_uid"] = user_uid
        new_contract = Contract(**data.model_dump())

        try:
            self.session.add(new_contract)
            await self.session.flush()
            contract_ref = self.build_contract_ref(name=new_contract.contract_type)
            statement = update(Contract).where(Contract.uid == new_contract.uid).values(contract_ref=contract_ref)
            await self.session.exec(statement)
            await self.session.commit()

            return new_contract
        except Exception:
            await self.session.rollback()
            raise BadRequest("Error creating contract")

    async def create_contract_details(self, contract_uid: UUID, data: CreateContractDetailsModel):
        pass

    async def create_tariff_period(self, contract_details_uid: UUID, tariff_period: int):
        pass

    async def create_tariff(self, tariff_period_uid: UUID, data: Tariff):
        pass

    async def update_contract_details(self, contract_uid: UUID, data: CreateContractDetailsModel):
        pass

    async def update_tariff_period(self, contract_details_uid: UUID, tariff_period: int):
        pass

    async def update_tariff(self, tariff_period_uid: UUID, data: Tariff):
        pass

    async def delete_contract_details(self, contract_uid: UUID):
        pass

    async def delete_tariff_period(self, contract_details_uid: UUID):
        pass

    async def delete_tariff(self, tariff_period_uid: UUID):
        pass


def get_contract_repo(session: AsyncSession = Depends(get_session)):
    return ContractRepository(session=session)
