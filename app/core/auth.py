import asyncio
import hashlib
import logging
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jwt import PyJWTError

from app.database.redis import async_redis_client
from app.shared.schema import PasscodeEnum, TokenIdentityModel

from .config import Config
from .exceptions import (
    BadRequest,
    ExpiredLink,
    InvalidLink,
    InvalidOTP,
    InvalidToken,
    RefreshTokenExpired,
    TokenExpired,
    TooManyAttempts,
    TooManyRequest,
)
from .logger import setup_logger

logger = setup_logger(__name__)


class Authentication:
    """Handles all authentication operations including JWT tokens, OTP passcodes, and URL-safe tokens."""

    ACCESS_TOKEN_EXPIRY_IN_SECONDS = 900  # 15 mins
    REFRESH_TOKEN_EXPIRY_IN_SECONDS = 604800  # 7 days

    VERIFY_LOGIN_PASSCODE_EXPIRY_IN_SECONDS = 300  # 5 mins
    RESEND_COOLDOWN = 60  # seconds
    MAX_ATTEMPTS = 5

    ACCOUNT_VERIFY_TOKEN_EXPIRY_IN_SECONDS = 86400  # 24 hours
    PWD_RESET_TOKEN_EXPIRY_IN_SECONDS = 3600  # 1 hour
    serializer: URLSafeTimedSerializer = URLSafeTimedSerializer(secret_key=Config.JWT_SECRET, salt=Config.EMAIL_SALT)

    @staticmethod
    def generate_otp(length: int = 6) -> str:
        """Generate a random OTP string of uppercase letters and digits.

        Args:
            length: Number of characters in the generated OTP. Defaults to 6.

        Returns:
            A random alphanumeric OTP string.
        """
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    async def generate_password_hash(password: str) -> str:
        """Hash a plain-text password using bcrypt in a thread pool.

        Args:
            password: The plain-text password to hash.

        Returns:
            The bcrypt-hashed password as a UTF-8 string.
        """
        return await asyncio.to_thread(
            lambda: bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        )

    @staticmethod
    async def verify_password(password: str, hash: str) -> bool:
        """Verify a plain-text password against a stored bcrypt hash.

        Args:
            password: The plain-text password to check.
            hash: The bcrypt hash to compare against.

        Returns:
            True if the password matches the hash, False otherwise.
        """
        return await asyncio.to_thread(bcrypt.checkpw, password.encode("utf-8"), hash.encode("utf-8"))

    @staticmethod
    async def create_token(
        user_data: TokenIdentityModel,
        response: Optional[Response] = None,
        expiry: timedelta = None,
        refresh: bool = False,
    ):
        """Create a signed JWT access or refresh token.

        For refresh tokens the JTI is also stored in Redis with the configured TTL.

        Args:
            user_data: Identity data to embed in the token payload.
            response: Optional FastAPI response object (kept for signature compatibility).
            expiry: Custom expiry duration. Defaults to class-level constants.
            refresh: If True, creates a refresh token with a reduced payload and persists the JTI in Redis.

        Returns:
            A tuple of (token_string, jti_string).
        """
        payload = {}

        if refresh:
            payload["user"] = user_data.model_dump(mode="json", include={"uid"})
        else:
            payload["user"] = user_data.model_dump(mode="json")

        payload["exp"] = int(
            (
                datetime.now()
                + (
                    expiry
                    if expiry is not None
                    else timedelta(
                        seconds=(
                            Authentication.REFRESH_TOKEN_EXPIRY_IN_SECONDS
                            if refresh
                            else Authentication.ACCESS_TOKEN_EXPIRY_IN_SECONDS
                        )
                    )
                )
            ).timestamp()
        )
        payload["jti"] = str(uuid4())
        payload["refresh"] = refresh
        token = jwt.encode(payload=payload, key=Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)

        if refresh:
            try:
                redis_key = payload["jti"]
                await async_redis_client.client.set(
                    name=redis_key,
                    value=token,
                    ex=Authentication.REFRESH_TOKEN_EXPIRY_IN_SECONDS,
                )
            except Exception as e:
                logging.error(f"Failed to initialize Redis client: {e}")
                pass

        return (token, payload["jti"])

    @staticmethod
    def set_refresh_token_cookie(response: Response, jti: str) -> None:
        """Set the refresh token JTI as an HTTP-only cookie on the response.

        Args:
            response: The FastAPI response object on which the cookie is set.
            jti: The JWT ID (JTI) of the refresh token to store in the cookie.

        Returns:
            None
        """
        is_relaxed = Config.is_relaxed_cookie_env

        response.set_cookie(
            key="refresh_token",
            value=jti,
            httponly=not is_relaxed,
            samesite=("none" if not is_relaxed else "lax"),
            secure=not is_relaxed,
            max_age=Authentication.REFRESH_TOKEN_EXPIRY_IN_SECONDS,
            path="/",
            domain=(None if is_relaxed else f".{Config.API_DOMAIN}"),
        )

    @staticmethod
    async def decode_token(token: str):
        """Decode and validate a JWT, raising typed exceptions for expired or invalid tokens.

        Args:
            token: The JWT string to decode.

        Returns:
            The decoded payload dictionary.

        Raises:
            InvalidToken: If the token cannot be decoded.
            RefreshTokenExpired: If the token is a refresh token that has expired.
            TokenExpired: If the access token has expired.
        """
        try:
            payload = jwt.decode(
                jwt=token,
                key=Config.JWT_SECRET,
                algorithms=[Config.JWT_ALGORITHM],
                options={"verify_exp": False},
            )
        except PyJWTError:
            raise InvalidToken()

        exp = payload.get("exp")
        if exp is not None and exp < int(datetime.now().timestamp()):
            if payload.get("refresh", False):
                raise RefreshTokenExpired()
            raise TokenExpired()

        return payload

    @staticmethod
    async def create_url_safe_token(data: dict, exp: Optional[int] = None, url_type: str = "verify") -> str:
        """Generate a URL-safe signed token and persist it in Redis with an expiry.

        Args:
            data: Dictionary of data to encode. Must include an 'email' key.
            exp: Custom expiry in seconds. Defaults to the TTL matching url_type.
            url_type: Token purpose — "verify" for account verification or any other value for password reset.

        Returns:
            The serialised URL-safe token string.

        Raises:
            BadRequest: If the token cannot be stored in Redis.
        """
        try:
            token = Authentication.serializer.dumps(data)
            redis_name = f"{url_type}:{data['email']}"

            ex = (
                exp
                if exp
                else (
                    Authentication.ACCOUNT_VERIFY_TOKEN_EXPIRY_IN_SECONDS
                    if url_type == "verify"
                    else Authentication.PWD_RESET_TOKEN_EXPIRY_IN_SECONDS
                )
            )

            success = await async_redis_client.client.set(
                name=redis_name,
                value=token,
                ex=ex,
            )
            if not success:
                raise ValueError("Failed to store token in Redis")

            return token
        except Exception as e:
            logging.error(f"Failed to set Redis key {redis_name}: {e}")
            raise BadRequest()

    @staticmethod
    async def decode_url_safe_token(token: str, url_type: str = "verify", expiry: Optional[int] = None) -> dict:
        """Decode and verify a URL-safe token, raising typed exceptions on failure.

        Args:
            token: The URL-safe token string to decode.
            url_type: Token purpose — "verify" for account verification or any other value for password reset.
            expiry: Custom max age in seconds. Defaults to the TTL matching url_type.

        Returns:
            The decoded data dictionary.

        Raises:
            ExpiredLink: If the token has expired.
            InvalidLink: If the token signature is invalid or any other error occurs.
        """
        try:
            max_age = (
                expiry
                if expiry
                else (
                    Authentication.ACCOUNT_VERIFY_TOKEN_EXPIRY_IN_SECONDS
                    if url_type == "verify"
                    else Authentication.PWD_RESET_TOKEN_EXPIRY_IN_SECONDS
                )
            )
            data = Authentication.serializer.loads(
                token,
                max_age=max_age,
            )
            return data

        except SignatureExpired:
            logging.error("Token expired")
            raise ExpiredLink()
        except BadSignature:
            logging.error("Invalid token")
            raise InvalidLink()
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            raise InvalidLink()

    @staticmethod
    async def generate_passcode(
        email: str,
        exp: Optional[int] = None,
        type: PasscodeEnum = PasscodeEnum.LOGIN.value,
    ):
        """Generate a hashed OTP for an email, enforcing a resend cooldown and resetting attempt counters.

        Args:
            email: The recipient email address used as part of the Redis key namespace.
            exp: Custom expiry in seconds for the OTP. Defaults to VERIFY_LOGIN_PASSCODE_EXPIRY_IN_SECONDS.
            type: Passcode type used to namespace the Redis key (e.g. PasscodeEnum.LOGIN).

        Returns:
            The plain-text OTP string to be delivered to the user.

        Raises:
            TooManyRequest: If a resend cooldown is currently active for this email.
            BadRequest: If storing the OTP in Redis fails.
        """
        otp = Authentication.generate_otp()
        redis_name = f"{type}:{email}"
        cooldown_key = f"{redis_name}:cooldown"

        if await async_redis_client.client.exists(cooldown_key):
            raise TooManyRequest("Please wait before requesting another code")

        ex = exp if exp else Authentication.VERIFY_LOGIN_PASSCODE_EXPIRY_IN_SECONDS
        hashed_otp = hashlib.sha256(otp.encode()).hexdigest()
        attempts_key = f"{redis_name}:attempts"

        try:
            async with async_redis_client.client.pipeline(transaction=True) as pipe:
                pipe.set(redis_name, hashed_otp, ex=ex)
                pipe.set(cooldown_key, "1", ex=Authentication.RESEND_COOLDOWN)
                pipe.delete(attempts_key)
                results = await pipe.execute()

            if not results[0]:
                raise ValueError("Failed to store OTP in Redis")

            return otp
        except Exception as e:
            logging.error(f"Failed to set Redis key {e}")
            raise BadRequest()

    @staticmethod
    async def decode_passcode(
        otp: str,
        email: str,
        type: PasscodeEnum = PasscodeEnum.LOGIN.value,
    ):
        """Validate a submitted OTP against the stored hash, tracking failed attempts.

        The OTP and its attempt counter are removed from Redis upon successful validation.

        Args:
            otp: The plain-text OTP submitted by the user.
            email: The email address whose OTP is being validated.
            type: Passcode type namespace used to locate the correct Redis key.

        Returns:
            True if the OTP is valid and has been consumed.

        Raises:
            InvalidOTP: If no stored OTP exists or the provided OTP does not match.
            TooManyAttempts: If the maximum number of failed attempts has been exceeded.
        """
        redis_name = f"{type}:{email}"
        attempts_key = f"{redis_name}:attempts"

        stored_otp = await async_redis_client.client.get(redis_name)

        if not stored_otp:
            raise InvalidOTP()

        async with async_redis_client.client.pipeline(transaction=False) as pipe:
            pipe.incr(attempts_key)
            pipe.expire(attempts_key, 300)
            attempts, _ = await pipe.execute()

        if attempts > Authentication.MAX_ATTEMPTS:
            await async_redis_client.client.delete(redis_name)
            raise TooManyAttempts("Too many incorrect attempts")

        hashed_input = hashlib.sha256(otp.encode()).hexdigest()

        if stored_otp != hashed_input:
            raise InvalidOTP()

        async with async_redis_client.client.pipeline(transaction=False) as pipe:
            pipe.delete(redis_name)
            pipe.delete(attempts_key)
            await pipe.execute()

        return True
