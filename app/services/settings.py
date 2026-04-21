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

    async def update_contract_general_settings(self, data: UpdateContractSettingsModel, token_payload: dict):
        user_payload = token_payload.get("user")
        user_uid = user_payload.get("uid")
        contract_settings = await self.get_contract_general_settings()
        result = await self.settings_repo.update_contract_settings(
            contract_settings=contract_settings, data=data, user_uid=user_uid
        )

        return result


def get_settings_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    return SettingsService(settings_repo=settings_repo)
