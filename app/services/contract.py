from fastapi import Depends
from sqlmodel import UUID

from app.core.exceptions import BadRequest, NotFound
from app.modules.contracts.model import Contract
from app.modules.contracts.repository import ContractRepository, get_contract_repo
from app.modules.contracts.schema import (
    ContractDetailsResponse,
    ContractResponse,
    ContractSystemModeEnum,
    ContractTypeEnum,
    CreateContractDetailsModel,
    CreateContractModel,
)


class ContractService:
    def __init__(self, contract_repo: ContractRepository = Depends(get_contract_repo)):
        self.contract_repo = contract_repo

    def _sanitize_contract_details(self, contract: Contract, data: CreateContractDetailsModel):
        # checks for on-grid system mode
        if contract.system_mode == ContractSystemModeEnum.ON_GRID.value:
            if not data.system_size_kwp:
                raise BadRequest("System size(kwp) is required for all on-grid system mode.")

            if not data.guaranteed_production_kwh_per_kwp:
                raise BadRequest("Guaranteed production(kwh/kwp) is required for all on-grid system mode.")

            if not data.grid_meter_reading_at_commissioning:
                raise BadRequest("Grid meter reading at comissioning is required for all on-grid system mode.")

        # checks for lease contracts
        if contract.contract_type == ContractTypeEnum.LEASE.value:
            if not data.equipment_lease_amount:
                raise BadRequest("Equipment lease amount is required for lease contracts.")
            if not data.maintenance_amount:
                raise BadRequest("maintenance amount is required for all lease contracts.")
            if not data.total:
                raise BadRequest("maintenance amount is required for all lease contracts.")

        # checks for ppa contracts
        if contract.contract_type == ContractTypeEnum.PPA.value:
            if not data.tariff_periods:
                raise BadRequest("Tariff is required for all PPA contracts.")
            if not data.monthly_baseline_consumption_kwh:
                raise BadRequest("monthly baseline consumption(kwh) is required for all PPA contracts.")
            if not data.minimum_consumption_monthly_kwh:
                raise BadRequest("minimum consumption monthly (kwh) is required for all PPA contracts.")
            if not data.minimum_spend:
                raise BadRequest("minimum consumption monthly (kwh) is required for all PPA contracts.")

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

    async def get_contract_invoices(self, contract_uid: UUID):
        pass

    async def create_contract_details(self, contract_uid: UUID, data: CreateContractDetailsModel):
        contract = await self.contract_repo.get_contract_by_uid(contract_uid=contract_uid)

        if not contract:
            raise NotFound(f"Contract with this {contract_uid} not found")

        self._sanitize_contract_details(contract=contract, data=data)
        await self.contract_repo.create_contract_details(contract_uid=contract_uid, data=data)

        return True

    async def update_contract_details(self, contract_details_uid: UUID, data: CreateContractDetailsModel):
        contract_details = await self.contract_repo.get_contract_details_by_uid(
            contract_details_uid=contract_details_uid
        )

        if not contract_details:
            raise NotFound(f"Contract details with this {contract_details_uid} not found")

        self._sanitize_contract_details(contract=contract_details.contract, data=data)
        await self.contract_repo.update_contract_details(contract_details_uid=contract_details_uid, data=data)

        return True


def get_contract_service(
    contract_repo: ContractRepository = Depends(get_contract_repo),
):
    return ContractService(contract_repo=contract_repo)
