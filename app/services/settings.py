from uuid import UUID

from fastapi import Depends

from app.modules.settings.repository import SettingsRepository, get_settings_repo
from app.modules.settings.schema import (
    CreateContractSettingsRateModel,
    RateHistoryRespModel,
    UpdateContractSettingsModel,
)


class SettingsService:
    def __init__(self, settings_repo: SettingsRepository = Depends(get_settings_repo)):
        self.settings_repo = settings_repo

    async def get_contract_general_settings(self):
        contract_settings = await self.settings_repo.get_contract_settings()

        if not contract_settings:
            new_contract_settings = await self.settings_repo.create_contract_settings()
            return new_contract_settings

        return contract_settings

    async def update_contract_general_settings(self, data: UpdateContractSettingsModel, token_payload: dict):
        user_payload = token_payload.get("user")
        user_uid = user_payload.get("uid")
        contract_settings = await self.get_contract_general_settings()
        result = await self.settings_repo.update_contract_settings(
            contract_settings=contract_settings, data=data, user_uid=user_uid
        )

        return result

    async def get_current_rate(self):
        current_rate = await self.settings_repo.get_current_rate()

        return RateHistoryRespModel.model_validate(current_rate)

    async def get_rate_history(self, contract_settings_uid: UUID):
        existing_rate_history = await self.settings_repo.get_rate_history(contract_settings_uid=contract_settings_uid)

        rate_history_list = [RateHistoryRespModel.model_validate(item) for item in existing_rate_history]

        return rate_history_list

    async def create_rate(
        self,
        contract_settings_uid: UUID,
        token_payload: dict,
        data: CreateContractSettingsRateModel,
    ):
        token_user = token_payload.get("user")
        user_uid = token_user.get("uid")
        new_rate = await self.settings_repo.create_rate(
            contract_settings_uid=contract_settings_uid, user_uid=user_uid, data=data
        )

        return RateHistoryRespModel.model_validate(new_rate)


def get_settings_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    return SettingsService(settings_repo=settings_repo)
