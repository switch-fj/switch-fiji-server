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
from app.modules.users.repository import UserRepository, get_user_repo
from app.modules.users.schema import CreateUserModel
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


class UserService:
    def __init__(self, user_repo: UserRepository = Depends(get_user_repo)):
        self.user_repo = user_repo

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

    async def get_current_user(self, token_payload: dict):
        user_email = token_payload["user"]["email"]
        user = await self.user_repo.get_user_by_mail(
            email=user_email,
        )

        if not user:
            raise NotFound("Client doesn't exist.")

        return UserResponseModel.model_validate(user)

    async def login(self, data: IdentityLoginModel):
        user = await self.user_repo.get_user_by_mail(email=data.email)

        if not user:
            raise WrongCredentials()

        auth_type = AuthType.PWD.value if user.password_hash else AuthType.OTP.value

        if not user.is_email_verified:
            await self._initiate_acct_verification_task(email=user.email)
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=user.is_email_verified,
                    auth_type=auth_type,
                ),
            )

        if not data.password:
            await self._initiate_verify_login_task(email=user.email)
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=user.is_email_verified,
                    auth_type=auth_type,
                ),
            )

        if not Authentication.verify_password(data.password, user.password_hash):
            raise WrongCredentials()

        token_identity_model = generate_token_identity_model(user)
        access_token = await Authentication.create_token(user_data=token_identity_model)

        return (
            token_identity_model,
            TokenModel(
                access_token=access_token,
                is_email_verified=user.is_email_verified,
                auth_type=auth_type,
            ),
        )

    async def register(self, token_payload: dict, data: CreateUserModel):
        token_user = token_payload.get("user")
        token_user_uid = token_user.get("uid")
        user = await self.user_repo.get_user_by_mail(email=data.email)

        if user:
            raise UserEmailExists()

        new_user = await self.user_repo.create_user(user_uid=token_user_uid, data=data)
        await self._initiate_acct_verification_task(email=new_user.email)

        return new_user

    async def request_login(self, data: EmailModel):
        user = await self.user_repo.get_user_by_mail(email=data.email)

        if not user:
            raise NotFound()

        if not user.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=user.is_email_verified,
                    auth_type=AuthType.OTP.value,
                ),
            )

        await self._initiate_verify_login_task(email=user.email)
        return True

    async def verify_login_code(self, data: VerifyLoginModel):
        user = await self.user_repo.get_user_by_mail(email=data.email)

        if not user:
            raise NotFound()

        if not user.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=user.is_email_verified,
                    auth_type=AuthType.OTP.value,
                ),
            )

        await Authentication.decode_passcode(otp=data.otp, email=data.email)
        token_identity_model = generate_token_identity_model(user)
        access_token = await Authentication.create_token(user_data=token_identity_model)

        return (
            token_identity_model,
            TokenModel(
                access_token=access_token,
                is_email_verified=user.is_email_verified,
                auth_type=AuthType.OTP.value,
            ),
        )

    async def verify_account(self, token: str):
        try:
            payload = await Authentication.decode_url_safe_token(token=token)
            user_email = payload.get("email")

            if not user_email:
                raise InvalidToken("Invalid token.")

            user = await self.user_repo.get_user_by_mail(user_email)

            if not user:
                raise NotFound("User doesn't exist.")

            if user.is_email_verified:
                return "Account already verified."

            await self.user_repo.verify_email(user=user)
            await redis_client.add_to_blocklist(token)

            return "Account verified successfully."

        except Exception as e:
            logger.error(f"Error verifying account: {e}")
            raise

    async def send_verification_email(self, data: EmailModel):
        user = await self.user_repo.get_user_by_mail(email=data.email)

        if not user:
            raise NotFound("user doesn't exist.")

        if user.is_email_verified:
            return "Account already verified."

        if await redis_client.client.exists(f"verify:{user.email}") > 0:
            return "A verification email was recently sent. Check your inbox."

        await self._initiate_acct_verification_task(email=user.email)

        return "Verification email sent. Check your inbox"


def get_user_service(user_repo: UserRepository = Depends(get_user_repo)):
    return UserService(user_repo=user_repo)
