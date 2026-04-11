from datetime import datetime
from email.utils import parseaddr
from typing import TYPE_CHECKING, Union
from uuid import UUID

from email_validator import EmailNotValidError, EmailSyntaxError
from fastapi import Request
from pydantic import validate_email
from starlette_context import context

from app.core.config import Config

if TYPE_CHECKING:
    from app.modules.clients.model import Client
    from app.modules.users.model import User


def build_link_from_base_url(path: str) -> str:
    base_url = context.get("base_url")
    return f"{base_url}api/v1/{path}"


def set_origin_from_request(request: Request) -> str:
    origin = request.headers.get("origin")
    if origin:
        return origin
    host = request.headers.get("host")
    scheme = request.url.scheme
    return f"{scheme}://{host}"


def get_request_origin() -> str:
    return context.get("origin")


def email_validator(value: str):
    try:
        validate_email(value)
        return value.lower()
    except EmailNotValidError:
        raise EmailSyntaxError("Invalid Email format")


def is_email(value):
    return "@" in parseaddr(value)[1]


def uuid_serializer(
    value: UUID,
):
    return str(value)


def generate_token_identity_model(user: Union["User", "Client"]):
    from app.shared.schema import TokenIdentityModel

    token_identity_data = TokenIdentityModel.model_validate(
        {
            "uid": str(user.uid),
            "email": getattr(user, "email", None) or getattr(user, "client_email", None),
            "identity": user.identity,
            "role": user.role or None,
            "is_email_verified": user.is_email_verified,
        }
    )

    return token_identity_data


def build_ref_no(name: str, id: int):
    prefix = name.upper().ljust(3, "X")[:3]
    current_year = str(datetime.now().year)

    return f"{prefix}-{current_year}-{str(id).zfill(4)}"


def build_redis_url(db: int = 0) -> str:
    if Config.REDIS_PASSWORD:
        return f"redis://:{Config.REDIS_PASSWORD}@{Config.REDIS_HOST}:{Config.REDIS_PORT}/{db}"
    return f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/{db}"
