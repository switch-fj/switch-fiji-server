from fastapi import Depends

from app.core.auth import Authentication
from app.core.exceptions import UserEmailExists, WrongCredentials
from app.modules.clients.repository import ClientRepository, get_client_repo
from app.modules.clients.schema import CreateClientModel
from app.shared.schema import AuthType, IdentityLoginModel, TokenModel
from app.utils import generate_token_identity_model


class ClientService:
    def __init__(self, client_repo: ClientRepository = Depends(get_client_repo)):
        self.client_repo = client_repo

    async def login(self, data: IdentityLoginModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise WrongCredentials()

        auth_type = AuthType.PWD.value if client.password_hash else AuthType.TOKEN.value

        if not client.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=client.is_email_verified,
                    auth_type=auth_type,
                ),
            )

        if not data.password:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=client.is_email_verified,
                    auth_type=auth_type,
                ),
            )

        if not Authentication.verify_password(data.password, client.password_hash):
            raise WrongCredentials()

        token_identity_model = generate_token_identity_model(client)
        access_token = await Authentication.create_token(user_data=token_identity_model)

        return (
            token_identity_model,
            TokenModel(
                access_token=access_token,
                is_email_verified=client.is_email_verified,
                auth_type=auth_type,
            ),
        )

    async def register(self, token_data: dict, data: CreateClientModel):
        token_user = token_data.get("user")
        token_user_uid = token_user.get("uid")
        client = await self.client_repo.get_client_by_mail(email=data.client_email)

        if client:
            raise UserEmailExists()

        new_client = await self.client_repo.create_client(user_uid=token_user_uid, data=data)
        return new_client


def get_client_service(client_repo: ClientRepository = Depends(get_client_repo)):
    return ClientService(client_repo=client_repo)
