from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.core.security import AccessTokenBearer
from app.modules.clients.schema import CreateClientModel
from app.services.client import ClientService, get_client_service
from app.shared.schema import IdentityTypeEnum, ServerRespModel, UserRoleEnum

engineer_router = APIRouter(prefix="/engineer", tags=["engineer"])


@engineer_router.get("")
async def root():
    return {"message": "engineer root 🚀"}


@engineer_router.post(
    "/register/client",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[bool],
)
async def register(
    data: CreateClientModel = Body(...),
    client_service: ClientService = Depends(get_client_service),
    token_data: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ENGINEER.value],
        )
    ),
):
    await client_service.register(token_data=token_data, data=data)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[bool](
            data=True,
            message="Client registered!.",
        ).model_dump(),
    )
