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
    """Base HTTP Bearer dependency that decodes and validates a JWT from the Authorization header."""

    def __init__(self, auto_error=True, is_not_protected: bool = False):
        """Initialise the bearer with optional unauthenticated-request tolerance.

        Args:
            auto_error: If True, FastAPI automatically returns 403 when no credentials are provided.
            is_not_protected: If True, allows requests without an Authorization header to pass through.
        """
        self.is_not_protected = is_not_protected
        super().__init__(
            auto_error=auto_error,
        )

    async def is_token_valid(self, token: str) -> Union[Dict[str, Any], bool]:
        """Decode a JWT and verify it is not in the Redis blocklist.

        Args:
            token: The raw JWT string extracted from the Authorization header.

        Returns:
            The decoded token payload dictionary if valid.

        Raises:
            RefreshTokenExpired: If the token is a refresh token that has expired.
            TokenExpired: If the access token has expired.
            InvalidToken: If the token cannot be decoded or is in the blocklist.
        """
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
        """Extract, validate, and verify the bearer token from the request.

        Args:
            request: The incoming FastAPI request object.

        Returns:
            The decoded token payload dictionary, or None if the route is unprotected and no token is present.

        Raises:
            InvalidToken: If the token is missing on a protected route or fails validation.
        """
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
        """Perform additional token data verification. Must be overridden by subclasses.

        Args:
            token_payload: The decoded JWT payload dictionary.

        Raises:
            NotImplementedError: Always, unless overridden.
        """
        raise NotImplementedError("Please override this method in child classes.")


class AccessTokenBearer(TokenBearer):
    """HTTP Bearer dependency that enforces access token type and optional identity/role requirements."""

    def __init__(
        self,
        required_identity: Optional[Union[int, list[int]]] = None,
        required_role: Optional[Union[int, list[int]]] = None,
        auto_error: bool = True,
        is_not_protected: bool = False,
    ):
        """Initialise with optional identity and role constraints.

        Args:
            required_identity: One or more IdentityTypeEnum values the token must match.
            required_role: One or more UserRoleEnum values the token must match (for USER identity only).
            auto_error: If True, FastAPI automatically returns 403 when credentials are absent.
            is_not_protected: If True, allows requests without an Authorization header.
        """
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
        """Verify the token is an access token and satisfies any identity or role requirements.

        Args:
            token_payload: The decoded JWT payload dictionary.

        Raises:
            AccessTokenRequired: If the token is a refresh token.
            InvalidToken: If the token payload is missing required identity fields.
            InsufficientPermissions: If the token's identity or role does not meet requirements.
        """
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
    """Convenience bearer dependency that restricts access to admin users only."""

    def __init__(
        self,
        auto_error: bool = True,
        is_not_protected: bool = False,
    ):
        """Initialise with hard-coded admin identity and role requirements.

        Args:
            auto_error: If True, FastAPI automatically returns 403 when credentials are absent.
            is_not_protected: If True, allows requests without an Authorization header.
        """
        super().__init__(
            auto_error=auto_error,
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ADMIN.value],
            is_not_protected=is_not_protected,
        )


class EngineerAccessBearer(AccessTokenBearer):
    """Convenience bearer dependency that restricts access to engineer users only."""

    def __init__(
        self,
        auto_error: bool = True,
        is_not_protected: bool = False,
    ):
        """Initialise with hard-coded engineer identity and role requirements.

        Args:
            auto_error: If True, FastAPI automatically returns 403 when credentials are absent.
            is_not_protected: If True, allows requests without an Authorization header.
        """
        super().__init__(
            auto_error=auto_error,
            required_identity=[IdentityTypeEnum.USER.value],
            required_role=[UserRoleEnum.ENGINEER.value],
            is_not_protected=is_not_protected,
        )
