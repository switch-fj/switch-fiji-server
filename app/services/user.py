from fastapi import Depends

from app.core.auth import Authentication
from app.core.exceptions import NotFound, UserEmailExists, WrongCredentials
from app.jobs.auth import send_verify_login_task
from app.modules.users.repository import UserRepository, get_user_repo
from app.modules.users.schema import CreateUserModel
from app.shared.schema import (
    AuthType,
    EmailModel,
    IdentityLoginModel,
    TokenModel,
    VerifyLoginModel,
)
from app.utils import generate_token_identity_model


class UserService:
    def __init__(self, user_repo: UserRepository = Depends(get_user_repo)):
        self.user_repo = user_repo

    async def _initiate_verify_login_task(self, email: str):
        text = await Authentication.generate_passcode(email=email)

        send_verify_login_task.delay(
            email=email,
            text=text,
        )

    async def login(self, data: IdentityLoginModel):
        user = await self.user_repo.get_user_by_mail(email=data.email)

        if not user:
            raise WrongCredentials()

        auth_type = AuthType.PWD.value if user.password_hash else AuthType.OTP.value

        if not user.is_email_verified:
            return (
                None,
                TokenModel(
                    access_token="",
                    is_email_verified=user.is_email_verified,
                    auth_type=auth_type,
                ),
            )

        if not data.password:
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


def get_user_service(user_repo: UserRepository = Depends(get_user_repo)):
    return UserService(user_repo=user_repo)
