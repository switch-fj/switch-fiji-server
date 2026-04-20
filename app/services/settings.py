from fastapi import Depends

from app.core.exceptions import NotFound
from app.modules.settings.repository import SettingsRepository, get_settings_repo
from app.modules.settings.schema import UpdateContractSettingsModel


class SettingsService:
    def __init__(self, settings_repo: SettingsRepository = Depends(get_settings_repo)):
        self.settings_repo = settings_repo

    async def get_contract_general_settings(self):
        contract = await self.settings_repo.get_contract_settings()

        if not contract:
            raise NotFound("General settings for contracts not found")

        return contract

    async def update_contract_general_settings(self, data: UpdateContractSettingsModel):
        contract_settings = await self.get_contract_general_settings()
        result = await self.settings_repo.update_contract_settings(contract_settings=contract_settings, data=data)

        return result


def get_settings_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    return SettingsService(settings_repo=settings_repo)
