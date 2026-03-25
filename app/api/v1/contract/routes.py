from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse
from sqlmodel import UUID

from app.core.security import AccessTokenBearer
from app.modules.contracts.schema import CreateContractDetailsModel, CreateContractModel
from app.services.contract import ContractService, get_contract_service
from app.shared.schema import IdentityTypeEnum, ServerRespModel, UserRoleEnum

contract_router = APIRouter(prefix="/contract", tags=["contract"])


@contract_router.post(
    "/new",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[str],
)
async def new_contract(
    data: CreateContractModel = Body(...),
    client_service: ContractService = Depends(get_contract_service),
    token_payload: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ADMIN.value],
        )
    ),
):
    contract_uid = await client_service.create_contract(token_payload=token_payload, data=data)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[str](
            data=contract_uid,
            message="New Contract created!.",
        ).model_dump(),
    )


@contract_router.post(
    "/details/{contract_uid}",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[str],
)
async def new_contract_details(
    contract_uid: str,
    data: CreateContractDetailsModel = Body(...),
    client_service: ContractService = Depends(get_contract_service),
    _: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ENGINEER.value],
        )
    ),
):
    contract_details_uid = await client_service.create_contract_details(contract_uid=UUID(contract_uid), data=data)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[str](
            data=contract_details_uid,
            message="Contract details created!.",
        ).model_dump(),
    )


@contract_router.put(
    "/details/{contract_details_uid}",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[bool],
)
async def edit_contract_details(
    contract_details_uid: str,
    data: CreateContractDetailsModel = Body(...),
    client_service: ContractService = Depends(get_contract_service),
    _: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ENGINEER.value],
        )
    ),
):
    resp = await client_service.update_contract_details(contract_details_uid=UUID(contract_details_uid), data=data)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[resp](
            data=contract_details_uid,
            message="Contract details updated!.",
        ).model_dump(),
    )
