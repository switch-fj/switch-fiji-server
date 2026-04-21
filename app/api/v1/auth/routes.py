from typing import Optional

from fastapi import APIRouter, Body, Cookie, Depends, status
from fastapi.responses import JSONResponse

from app.core.auth import Authentication
from app.core.security import AccessTokenBearer
from app.modules.users.schema import CreateUserModel
from app.services.user import UserService, get_user_service
from app.shared.schema import (
    AuthType,
    EmailModel,
    IdentityLoginModel,
    IdentityTypeEnum,
    ServerRespModel,
    TokenModel,
    UserResponseModel,
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
    refresh_jti, token_model = await user_service.login(data=data)
    access_token = token_model.access_token
    auth_type = token_model.auth_type

    message = ""

    if access_token:
        message = "user logged in successfully!"
    else:
        if auth_type == AuthType.PWD.value:
            message = "Provide user password."
        elif auth_type == AuthType.OTP.value:
            message = "user login otp sent to inbox."

    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](data=token_model, message=message).model_dump(),
    )

    if refresh_jti:
        Authentication.set_refresh_token_cookie(response=response, jti=refresh_jti)

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
    return ServerRespModel[bool](
        data=True,
        message="User registered!.",
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
            message="User verified!",
        ).model_dump(),
    )

    if token_identity_model:
        refresh_token = await Authentication.create_token(user_data=token_identity_model, refresh=True)
        refresh_token_payload = await Authentication.decode_token(refresh_token)
        refresh_jti = refresh_token_payload["jti"]
        Authentication.set_refresh_token_cookie(response=response, jti=refresh_jti)

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

    return ServerRespModel[TokenModel](
        data=True,
        message=resp,
    )


@auth_router.get(
    "/profile",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[UserResponseModel],
)
async def profile(
    token_payload: TokenModel = Depends(AccessTokenBearer(required_identity=[IdentityTypeEnum.USER.value])),
    user_service: UserService = Depends(get_user_service),
):
    user_resp = await user_service.get_current_user(token_payload=token_payload)

    return ServerRespModel[UserResponseModel](
        data=user_resp,
        message="Profile retrieved",
    )


@auth_router.post(
    "/new-access-token",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[TokenModel],
)
async def get_new_user_access_token(
    token_jti: Optional[str] = Cookie(None, alias="refresh_token"),
    user_service: UserService = Depends(get_user_service),
):
    new_access_token, is_email_verified, auth_type = await user_service.new_access_token(token_jti=token_jti)

    return ServerRespModel[TokenModel](
        data={
            "access_token": new_access_token,
            "is_email_verified": is_email_verified,
            "auth_type": auth_type,
        },
        message="new access token generated.",
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

    return ServerRespModel[bool](
        data=True,
        message=resp,
    )
