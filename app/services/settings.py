from fastapi import Depends

from app.modules.settings.repository import SettingsRepository, get_settings_repo
from app.modules.settings.schema import (
    EFLRateHistoryRespModel,
    UpdateContractSettingsModel,
    VATRateHistoryRespModel,
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

    async def get_current_efl_rate(self):
        current_efl_rate = await self.settings_repo.get_current_efl_rate()

        return EFLRateHistoryRespModel.model_validate(current_efl_rate)

    async def get_current_vat_rate(self):
        current_vat_rate = await self.settings_repo.get_current_vat_rate()

        return VATRateHistoryRespModel.model_validate(current_vat_rate)

    async def get_efl_rate_history(self):
        existing_efl_rate_history = await self.settings_repo.get_efl_rate_history()

        efl_rate_history_list = [EFLRateHistoryRespModel.model_validate(item) for item in existing_efl_rate_history]

        return efl_rate_history_list

    async def get_vat_rate_history(self):
        existing_vat_rate_history = await self.settings_repo.get_vat_rate_history()

        vat_rate_history_list = [VATRateHistoryRespModel.model_validate(item) for item in existing_vat_rate_history]

        return vat_rate_history_list


def get_settings_service(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    return SettingsService(settings_repo=settings_repo)
