import logging
from typing import Any, Dict, Optional, Union

from fastapi import Request
from fastapi.security import HTTPBearer

from app.core.auth import Authentication
from app.core.exceptions import (
    AccessTokenRequired,
    InsufficientPermissions,
    InvalidToken,
    RefreshTokenExpired,
    TokenExpired,
)
from app.database.redis import async_redis_client
from app.shared.schema import IdentityTypeEnum, UserRoleEnum


class TokenBearer(HTTPBearer):
    def __init__(self, auto_error=True, is_not_protected: bool = False):
        self.is_not_protected = is_not_protected
        super().__init__(
            auto_error=auto_error,
        )

    async def is_token_valid(self, token: str) -> Union[Dict[str, Any], bool]:
        try:
            token_payload = await Authentication.decode_token(token)

            if await async_redis_client.in_blocklist(token_payload["jti"]):
                raise InvalidToken()

            return token_payload
        except RefreshTokenExpired as e:
            logging.warning(f"RefreshTokenExpired caught in is_token_valid: {e}")
            raise
        except TokenExpired as e:
            logging.warning(f"TokenExpired caught in is_token_valid: {e}")
            raise
        except Exception as e:
            logging.warning(f"Other exception in is_token_valid: {type(e).__name__}: {e}")
            raise InvalidToken()

    async def __call__(self, request: Request):
        auth_header = request.headers.get("Authorization")

        if self.is_not_protected and not auth_header:
            return None

        cred = await super().__call__(request)
        token = cred.credentials

        token_payload = await self.is_token_valid(token)
        if not token_payload:
            raise InvalidToken()

        await self.verify_token_data(token_payload)
        return token_payload

    async def verify_token_data(self, token_payload) -> None:
        raise NotImplementedError("Please override this method in child classes.")


class AccessTokenBearer(TokenBearer):
    def __init__(
        self,
        required_identity: Optional[Union[int, list[int]]] = None,
        required_role: Optional[Union[int, list[int]]] = None,
        auto_error: bool = True,
        is_not_protected: bool = False,
    ):
        super().__init__(auto_error=auto_error, is_not_protected=is_not_protected)
        if isinstance(required_identity, int):
            self.required_identity = [required_identity]
        else:
            self.required_identity = required_identity or []

        if isinstance(required_role, int):
            self.required_role = [required_role]
        else:
            self.required_role = required_role or []

    async def verify_token_data(self, token_payload: dict):
        if token_payload.get("refresh"):
            raise AccessTokenRequired()

        token_user = token_payload.get("user")
        if not token_user:
            raise InvalidToken()

        identity = token_user.get("identity")
        if identity is None:
            raise InvalidToken()

        if self.required_identity:
            if identity not in self.required_identity:
                raise InsufficientPermissions()

        if self.required_role:
            role = token_user.get("role")
            if identity == IdentityTypeEnum.USER.value:
                if role is None or role not in self.required_role:
                    raise InsufficientPermissions()


class AdminAccessBearer(AccessTokenBearer):
    def __init__(
        self,
        auto_error: bool = True,
        is_not_protected: bool = False,
    ):
        super().__init__(
            auto_error=auto_error,
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ADMIN.value],
            is_not_protected=is_not_protected,
        )


class EngineerAccessBearer(AccessTokenBearer):
    def __init__(
        self,
        auto_error: bool = True,
        is_not_protected: bool = False,
    ):
        super().__init__(
            auto_error=auto_error,
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ENGINEER.value],
            is_not_protected=is_not_protected,
        )
