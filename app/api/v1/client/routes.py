from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.core.auth import Authentication
from app.services.client import ClientService, get_client_service
from app.shared.schema import IdentityLoginModel, ServerRespModel, TokenModel

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
