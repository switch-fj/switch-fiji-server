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
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_contract_settings(self):
        statement = select(ContractSettings)
        result = await self.session.exec(statement)
        contract_settings = result.first()

        return contract_settings

    async def create_contract_settings(self):
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
    return SettingsRepository(session=session)
