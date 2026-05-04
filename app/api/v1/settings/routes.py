from fastapi import APIRouter, Depends, status

from app.core.security import AdminAccessBearer
from app.modules.settings.schema import (
    ContractSettingsModel,
    EFLRateHistoryRespModel,
    UpdateContractSettingsModel,
    VATRateHistoryRespModel,
)
from app.services.settings import SettingsService, get_settings_service
from app.shared.schema import (
    ServerRespModel,
)

settings_router = APIRouter(prefix="/settings", tags=["settings"])


@settings_router.get(
    "/contracts-settings",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[ContractSettingsModel],
)
async def get_contracts_general_settings(
    contract_settings_service: SettingsService = Depends(get_settings_service),
    _: dict = Depends(AdminAccessBearer()),
):
    contract_settings = await contract_settings_service.get_contract_general_settings()

    return ServerRespModel[ContractSettingsModel](
        data=ContractSettingsModel.model_validate(contract_settings),
        message="contract general settings retrieved",
    )


@settings_router.patch(
    "/contracts-settings",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ServerRespModel[bool],
)
async def update_contracts_generat_settings(
    data: UpdateContractSettingsModel,
    contract_settings_service: SettingsService = Depends(get_settings_service),
    token_payload: dict = Depends(AdminAccessBearer()),
):
    resp = await contract_settings_service.update_contract_general_settings(data=data, token_payload=token_payload)

    return ServerRespModel[bool](data=resp, message="contract general settings updated")


@settings_router.get(
    "/efl-rate-history",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[list[EFLRateHistoryRespModel]],
)
async def get_efl_rate_history(
    contract_settings_service: SettingsService = Depends(get_settings_service),
    _: dict = Depends(AdminAccessBearer()),
):
    resp = await contract_settings_service.get_efl_rate_history()

    return ServerRespModel[list[EFLRateHistoryRespModel]](data=resp, message="efl rate history retrieved!")


@settings_router.get(
    "/vat-rate-history",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[list[VATRateHistoryRespModel]],
)
async def get_vat_rate_history(
    contract_settings_service: SettingsService = Depends(get_settings_service),
    _: dict = Depends(AdminAccessBearer()),
):
    resp = await contract_settings_service.get_vat_rate_history()

    return ServerRespModel[list[VATRateHistoryRespModel]](data=resp, message="vat rate history retrieved!")
