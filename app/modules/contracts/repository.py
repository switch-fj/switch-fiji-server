import json
from datetime import datetime
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import selectinload
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import Authentication
from app.core.exceptions import BadRequest, NotFound
from app.database.postgres import get_session
from app.modules.contracts.model import Contract, ContractDetails
from app.modules.contracts.schema import (
    ContractSystemModeEnum,
    ContractTypeEnum,
    CreateContractDetailsModel,
    CreateContractModel,
)


class ContractRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _build_contract_ref(self, name: str):
        prefix = f"{name.upper()[0]}C"
        current_year = str(datetime.now().year)

        return f"{prefix}-{current_year}-{Authentication.generate_otp(4)}"

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

    async def get_contract_by_uid(self, contract_uid: UUID):
        statement = select(Contract).where(Contract.uid == contract_uid)
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
        new_contract = Contract(**data.model_dump())

        try:
            self.session.add(new_contract)
            await self.session.flush()
            contract_ref = self._build_contract_ref(name=new_contract.contract_type)
            statement = update(Contract).where(Contract.uid == new_contract.uid).values(contract_ref=contract_ref)
            await self.session.exec(statement)
            await self.session.commit()

            return new_contract
        except Exception:
            await self.session.rollback()
            raise BadRequest("Error creating contract")

    async def create_contract_details(self, contract_uid: UUID, data: CreateContractDetailsModel):
        # check if contract uid exists
        contract = await self.get_contract_by_uid(contract_uid=contract_uid)

        if not contract:
            raise NotFound("Contract not found.")

        self._sanitize_contract_details(contract=contract, data=data)

        try:
            # now, create it!
            data_dict = data.model_dump()

            if data.tariffs and data.tariff_periods:
                data_dict.pop("tariffs", None)
                data_dict["tariff_slots"] = json.dumps(data.tariffs)

            contract_details = ContractDetails(**data_dict)
            await self.session.add(contract_details)
            await self.session.commit()

            return contract_details
        except Exception:
            await self.session.rollback()

    async def update_contract_details(self, contract_details_uid: UUID, data: CreateContractDetailsModel):
        contract_details = await self.get_contract_details_by_uid(contract_details_uid=contract_details_uid)

        if not contract_details:
            raise NotFound("Contract details not found.")

        self._sanitize_contract_details(contract=contract_details.contract, data=data)

        try:
            # now, create it!
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
            raise BadRequest(f"{e}")
        except Exception:
            await self.session.rollback()
            raise


def get_contract_repo(session: AsyncSession = Depends(get_session)):
    return ContractRepository(session=session)
