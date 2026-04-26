from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

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
    _, token_model = await client_service.login(data=data)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=token_model,
            message="Client token generated.",
        ).model_dump(),
    )


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
    return ServerRespModel[bool](
        data=True,
        message="Login code sent to your email!.",
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
    _, token_model = await client_service.verify_login_code(data=data)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=ServerRespModel[TokenModel](
            data=token_model,
            message="Client token generated.",
        ).model_dump(),
    )


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

    return ServerRespModel[TokenModel](
        data=True,
        message=resp,
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

    return ServerRespModel[TokenModel](
        data=user_resp,
        message="Profile retrieved",
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

    return ServerRespModel[TokenModel](
        data=True,
        message=resp,
    )
