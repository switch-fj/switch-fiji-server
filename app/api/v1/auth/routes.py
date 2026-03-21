from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.core.auth import Authentication
from app.core.security import AccessTokenBearer
from app.modules.users.schema import CreateUserModel
from app.services.user import UserService, get_user_service
from app.shared.schema import (
    IdentityLoginModel,
    IdentityTypeEnum,
    ServerRespModel,
    TokenModel,
    UserRoleEnum,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[TokenModel],
)
async def login(
    data: IdentityLoginModel = Body(...),
    user_service: UserService = Depends(get_user_service),
):
    token_identity_model, token_model = await user_service.login(data=data)
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=token_model,
            message="User token generated.",
        ).model_dump(),
    )

    if token_identity_model:
        await Authentication.create_token(user_data=token_identity_model, refresh=True, response=response)

    return response


@auth_router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ServerRespModel[bool],
)
async def register(
    data: CreateUserModel = Body(...),
    user_service: UserService = Depends(get_user_service),
    token_data: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ADMIN.value],
        )
    ),
):
    await user_service.register(token_data=token_data, data=data)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[bool](
            data=True,
            message="User registered!.",
        ).model_dump(),
    )
