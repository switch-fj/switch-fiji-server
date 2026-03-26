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
from jwt import ExpiredSignatureError, PyJWTError

from app.database.redis import redis_client
from app.shared.schema import PasscodeEnum, TokenIdentityModel

from .config import Config
from .exceptions import (
    BadRequest,
    ExpiredLink,
    InvalidLink,
    InvalidToken,
    RefreshTokenExpired,
    TokenExpired,
    TooManyAttempts,
    TooManyRequest,
)
from .logger import setup_logger

logger = setup_logger(__name__)


class Authentication:
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
        alphabet = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def generate_password_hash(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    @staticmethod
    def verify_password(password: str, hash: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), hash.encode("utf-8"))

    @staticmethod
    async def create_token(
        user_data: TokenIdentityModel,
        response: Optional[Response] = None,
        expiry: timedelta = None,
        refresh: bool = False,
    ) -> str:
        payload = {}

        if refresh:
            payload["user"] = user_data.model_dump(mode="json", include={"uid", "id"})
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
                await redis_client.client.set(
                    name=redis_key,
                    value=token,
                    ex=Authentication.REFRESH_TOKEN_EXPIRY_IN_SECONDS,
                )

                if response:
                    response.set_cookie(
                        key="refresh_token",
                        value=redis_key,
                        httponly=True,
                        samesite=("lax" if Config.ENV == "development" else "none"),
                        secure=Config.ENV != "development",
                        max_age=Authentication.REFRESH_TOKEN_EXPIRY_IN_SECONDS,
                        path="/",
                        domain=(None if Config.ENV == "development" else f".{Config.API_DOMAIN}"),
                    )

            except Exception as e:
                logging.error(f"Failed to initialize Redis client: {e}")
                pass

        return token

    @staticmethod
    async def decode_token(token: str):
        try:
            token_payload = jwt.decode(
                jwt=token,
                key=Config.JWT_SECRET,
                algorithms=[Config.JWT_ALGORITHM],
                verify=True,
            )
            return token_payload
        except ExpiredSignatureError:
            try:
                unverified_payload = jwt.decode(
                    jwt=token,
                    key=Config.JWT_SECRET,
                    algorithms=[Config.JWT_ALGORITHM],
                    options={"verify_exp": False},
                )
                is_refresh = unverified_payload.get("refresh", False)
                logging.warning(f"Token expired. Is refresh: {is_refresh}")

                if is_refresh:
                    logging.warning("Raising RefreshTokenExpired")
                    raise RefreshTokenExpired()
                else:
                    logging.warning("Raising TokenExpired")
                    raise TokenExpired()

            except (KeyError, ValueError, TypeError) as decode_error:
                logging.warning(f"Could not decode expired token payload: {decode_error}")
                raise TokenExpired()
            except RefreshTokenExpired:
                raise
            except TokenExpired:
                raise
        except PyJWTError:
            logging.exception("JWT decoding failed.")
            raise InvalidToken()

    @staticmethod
    async def create_url_safe_token(data: dict, exp: Optional[int] = None, url_type: str = "verify") -> str:
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

            success = await redis_client.client.set(
                name=redis_name,
                value=token,
                ex=ex,
            )
            if not success:
                raise ValueError("Failed to store token in Redis")

            stored_token = await redis_client.client.get(redis_name)
            if stored_token != token:
                raise ValueError(f"Token verification failed for {redis_name}")

            logger.info(f"Successfully stored token in Redis for {redis_name}")

            return token
        except Exception as e:
            logging.error(f"Failed to set Redis key {redis_name}: {e}")
            raise BadRequest()

    @staticmethod
    async def decode_url_safe_token(token: str, url_type: str = "verify", expiry: Optional[int] = None) -> dict:
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
        otp = Authentication.generate_otp()
        redis_name = f"{type}:{email}"
        cooldown_key = f"{redis_name}:cooldown"

        if await redis_client.client.exists(cooldown_key):
            raise TooManyRequest("Please wait before requesting another code")

        ex = exp if exp else Authentication.VERIFY_LOGIN_PASSCODE_EXPIRY_IN_SECONDS
        hashed_otp = hashlib.sha256(otp.encode()).hexdigest()

        try:
            resp = await redis_client.client.set(
                name=redis_name,
                value=hashed_otp,
                ex=ex,
            )

            if not resp:
                raise ValueError("Failed to store token in Redis")

            await redis_client.client.set(
                name=cooldown_key,
                value="1",
                ex=Authentication.RESEND_COOLDOWN,
            )

            attempts_key = f"{redis_name}:attempts"
            await redis_client.client.delete(attempts_key)

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
        redis_name = f"{type}:{email}"
        attempts_key = f"{redis_name}:attempts"

        stored_otp = await redis_client.client.get(redis_name)

        if not stored_otp:
            raise InvalidLink()

        attempts = await redis_client.client.incr(attempts_key)
        await redis_client.client.expire(attempts_key, 300)

        if attempts > Authentication.MAX_ATTEMPTS:
            await redis_client.client.delete(redis_name)
            raise TooManyAttempts("Too many incorrect attempts")

        hashed_input = hashlib.sha256(otp.encode()).hexdigest()

        if stored_otp != hashed_input:
            raise InvalidLink()

        await redis_client.client.delete(redis_name)
        await redis_client.client.delete(attempts_key)

        return True
