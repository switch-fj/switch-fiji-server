from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.core.auth import Authentication
from app.core.security import AccessTokenBearer
from app.services.client import ClientService, get_client_service
from app.shared.schema import (
    EmailModel,
    IdentityLoginModel,
    IdentityTypeEnum,
    ServerRespModel,
    TokenModel,
    UserRoleEnum,
    VerifyLoginModel,
)

client_router = APIRouter(prefix="/client", tags=["client"])


@client_router.post(
    "/auth/login",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[TokenModel],
)
async def client_login(
    data: IdentityLoginModel = Body(...),
    client_service: ClientService = Depends(get_client_service),
):
    token_identity_model, token_model = await client_service.login(data=data)
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=token_model,
            message="Client token generated.",
        ).model_dump(),
    )

    if token_identity_model:
        await Authentication.create_token(user_data=token_identity_model, refresh=True, response=response)

    return response


@client_router.post(
    "/auth/login/request",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def request_login(
    data: EmailModel = Body(...),
    client_service: ClientService = Depends(get_client_service),
):
    await client_service.request_login(data=data)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[bool](
            data=True,
            message="Login code sent to your email!.",
        ).model_dump(),
    )


@client_router.post(
    "/login/verify",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[TokenModel],
)
async def verify_login_code(
    data: VerifyLoginModel = Body(...),
    client_service: ClientService = Depends(get_client_service),
):
    token_identity_model, token_model = await client_service.verify_login_code(data=data)
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=token_model,
            message="Client token generated.",
        ).model_dump(),
    )

    if token_identity_model:
        await Authentication.create_token(user_data=token_identity_model, refresh=True, response=response)

    return response


@client_router.post(
    "/verify/send",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def send_verify_acct(
    email: EmailModel,
    client_service: ClientService = Depends(get_client_service),
):
    resp = await client_service.send_verification_email(email=email)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=True,
            message=resp,
        ).model_dump(),
    )


@client_router.get(
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
    client_service: ClientService = Depends(get_client_service),
):
    user_resp = await client_service.get_current_client(token_payload=token_payload)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=user_resp,
            message="Profile retrieved",
        ).model_dump(),
    )


@client_router.get(
    "/verify/acct/{token}",
    status_code=status.HTTP_200_OK,
    response_model=ServerRespModel[bool],
)
async def verify_acct(
    token: str,
    client_service: ClientService = Depends(get_client_service),
):
    resp = await client_service.verify_account(token=token)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=True,
            message=resp,
        ).model_dump(),
    )
