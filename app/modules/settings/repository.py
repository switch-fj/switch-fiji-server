from fastapi import Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import setup_logger
from app.database.postgres import get_session
from app.modules.settings.model import ContractSettings
from app.modules.settings.schema import UpdateContractSettingsModel

logger = setup_logger(__name__)


class SettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_contract_settings(self):
        statement = select(ContractSettings)
        result = await self.session.exec(statement)
        contract_settings = result.first()

        return contract_settings

    async def update_contract_settings(self, contract_settings: ContractSettings, data: UpdateContractSettingsModel):
        data_dict = data.model_dump(exclude_none=True)

        if len(list(data_dict.keys())) == 0:
            return True

        self.session.add(contract_settings)
        await self.session.commit()
        await self.session.refresh(contract_settings)

        return True


def get_settings_repo(session: AsyncSession = Depends(get_session)):
    return SettingsRepository(session=session)
