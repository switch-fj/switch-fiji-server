from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.core.auth import Authentication
from app.core.security import AccessTokenBearer
from app.modules.users.schema import CreateUserModel
from app.services.user import UserService, get_user_service
from app.shared.schema import (
    EmailModel,
    IdentityLoginModel,
    IdentityTypeEnum,
    ServerRespModel,
    TokenModel,
    UserRoleEnum,
    VerifyLoginModel,
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
    token_payload: dict = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ADMIN.value],
        )
    ),
):
    await user_service.register(token_payload=token_payload, data=data)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[bool](
            data=True,
            message="User registered!.",
        ).model_dump(),
    )


@auth_router.post(
    "/login/request",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def request_login(
    data: EmailModel = Body(...),
    user_service: UserService = Depends(get_user_service),
):
    await user_service.request_login(data=data)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[bool](
            data=True,
            message="Login code sent to your email!.",
        ).model_dump(),
    )


@auth_router.post(
    "/login/verify",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[TokenModel],
)
async def verify_login_code(
    data: VerifyLoginModel = Body(...),
    user_service: UserService = Depends(get_user_service),
):
    token_identity_model, token_model = await user_service.verify_login_code(data=data)
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
    "/verify/send",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def send_verify_acct(
    email: EmailModel,
    user_service: UserService = Depends(get_user_service),
):
    resp = await user_service.send_verification_email(email=email)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=True,
            message=resp,
        ).model_dump(),
    )


@auth_router.get(
    "/profile",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def profile(
    token_payload: TokenModel = Depends(
        AccessTokenBearer(
            required_identity=[IdentityTypeEnum.CLIENT.value],
            required_role=[UserRoleEnum.ADMIN.value],
        )
    ),
    user_service: UserService = Depends(get_user_service),
):
    user_resp = await user_service.get_current_client(token_payload=token_payload)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=user_resp,
            message="Profile retrieved",
        ).model_dump(),
    )


@auth_router.get(
    "/verify/acct/{token}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def verify_acct(
    token: str,
    user_service: UserService = Depends(get_user_service),
):
    resp = await user_service.verify_account(token=token)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=True,
            message=resp,
        ).model_dump(),
    )
