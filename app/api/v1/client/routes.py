from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.core.auth import Authentication
from app.services.client import ClientService, get_client_service
from app.shared.schema import (
    EmailModel,
    IdentityLoginModel,
    ServerRespModel,
    TokenModel,
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
