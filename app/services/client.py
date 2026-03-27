from fastapi import Depends

from app.core.auth import Authentication
from app.core.exceptions import (
    InvalidToken,
    NotFound,
    UserEmailExists,
    WrongCredentials,
)
from app.core.logger import setup_logger
from app.database.redis import redis_client
from app.jobs.auth import send_email_verification_task, send_verify_login_task
from app.modules.clients.repository import ClientRepository, get_client_repo
from app.modules.clients.schema import CreateClientModel
from app.shared.schema import (
    AuthType,
    EmailModel,
    IdentityLoginModel,
    TokenModel,
    UserResponseModel,
    VerifyLoginModel,
)
from app.utils import generate_token_identity_model, get_request_origin

logger = setup_logger(__name__)


class ClientService:
    def __init__(self, client_repo: ClientRepository = Depends(get_client_repo)):
        self.client_repo = client_repo

    async def _initiate_verify_login_task(self, email: str):
        text = await Authentication.generate_passcode(email=email)

        send_verify_login_task.delay(
            email=email,
            text=text,
        )

    async def _initiate_acct_verification_task(self, email: str):
        token_payload = {"email": email}
        email_token = await Authentication.create_url_safe_token(data=token_payload)
        verification_url = f"{get_request_origin()}/auth/verify?token={email_token}"

        send_email_verification_task.delay(
            email=email,
            verification_url=verification_url,
        )

    async def get_current_client(self, token_payload: dict):
        client_email = token_payload["user"]["email"]
        client = await self.client_repo.get_client_by_mail(
            email=client_email,
        )

        if not client:
            raise NotFound("Client doesn't exist.")

        return UserResponseModel.model_validate(client)

    async def login(self, data: IdentityLoginModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise WrongCredentials()

        auth_type = AuthType.PWD.value if client.password_hash else AuthType.OTP.value

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

    async def register(self, token_payload: dict, data: CreateClientModel):
        token_user = token_payload.get("user")
        token_user_uid = token_user.get("uid")
        client = await self.client_repo.get_client_by_mail(email=data.client_email)

        if client:
            raise UserEmailExists()

        new_client = await self.client_repo.create_client(user_uid=token_user_uid, data=data)
        return new_client

    async def request_login(self, data: EmailModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise NotFound()

        if not client.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=client.is_email_verified,
                    auth_type=AuthType.OTP.value,
                ),
            )

        await self._initiate_verify_login_task(email=client.client_email)
        return True

    async def verify_login_code(self, data: VerifyLoginModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise NotFound()

        if not client.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=client.is_email_verified,
                    auth_type=AuthType.OTP.value,
                ),
            )

        await Authentication.decode_passcode(otp=data.otp, email=data.email)
        token_identity_model = generate_token_identity_model(client)
        access_token = await Authentication.create_token(user_data=token_identity_model)

        return (
            token_identity_model,
            TokenModel(
                access_token=access_token,
                is_email_verified=client.is_email_verified,
                auth_type=AuthType.OTP.value,
            ),
        )

    async def verify_account(self, token: str):
        try:
            payload = await Authentication.decode_url_safe_token(token=token)
            client_email = payload.get("email")

            if not client_email:
                raise InvalidToken("Invalid token.")

            client = await self.client_repo.get_client_by_mail(client_email)

            if not client:
                raise NotFound("User doesn't exist.")

            if client.is_email_verified:
                return "Account already verified."

            await self.client_repo.verify_email(client=client)
            await redis_client.add_to_blocklist(token)

            return "Account verified successfully."

        except Exception as e:
            logger.error(f"Error verifying account: {e}")
            raise

    async def send_verification_email(self, data: EmailModel):
        client = await self.client_repo.get_client_by_mail(email=data.email)

        if not client:
            raise NotFound("client doesn't exist.")

        if client.is_email_verified:
            return "Account already verified."

        if await redis_client.client.exists(f"verify:{client.client_email}") > 0:
            return "A verification email was recently sent. Check your inbox."

        await self._initiate_acct_verification_task(email=client.client_email)

        return "Verification email sent. Check your inbox"


def get_client_service(client_repo: ClientRepository = Depends(get_client_repo)):
    return ClientService(client_repo=client_repo)
