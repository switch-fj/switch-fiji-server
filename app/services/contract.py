from fastapi import Depends
from sqlmodel import UUID

from app.core.exceptions import NotFound
from app.modules.contracts.repository import ContractRepository, get_contract_repo
from app.modules.contracts.schema import (
    ContractDetailsResponse,
    ContractResponse,
    CreateContractDetailsModel,
    CreateContractModel,
)


class ContractService:
    def __init__(self, contract_repo: ContractRepository = Depends(get_contract_repo)):
        self.contract_repo = contract_repo

    async def create_contract(self, token_payload: dict, data: CreateContractModel):
        token_user = token_payload.get("user")
        user_uid = token_user.get("uid")

        contract = await self.contract_repo.create_contract(user_uid=user_uid, data=data)

        return str(contract.uid)

    async def get_contract_by_uid(self, contract_uid: UUID):
        contract = await self.contract_repo.get_contract_by_uid(contract_uid=contract_uid)

        if not contract:
            raise NotFound(f"Contract with this {contract_uid} not found")

        return ContractResponse.model_validate(contract)

    async def get_contract_details_by_uid(self, contract_details_uid: UUID):
        contract = await self.contract_repo.get_contract_details_by_uid(contract_details_uid=contract_details_uid)

        if not contract:
            raise NotFound(f"Contract details with this {contract_details_uid} not found")

        return ContractDetailsResponse.model_validate(contract)

    async def create_contract_details(self, contract_uid: UUID, data: CreateContractDetailsModel):
        await self.contract_repo.create_contract_details(contract_uid=contract_uid, data=data)

        return True

    async def update_contract_details(self, contract_details_uid: UUID, data: CreateContractDetailsModel):
        await self.contract_repo.update_contract_details(contract_details_uid=contract_details_uid, data=data)

        return True


def get_contract_service(
    contract_repo: ContractRepository = Depends(get_contract_repo),
):
    return ContractService(contract_repo=contract_repo)
