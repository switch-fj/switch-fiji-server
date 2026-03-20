from email.utils import parseaddr
from uuid import UUID

from email_validator import EmailNotValidError, EmailSyntaxError
from fastapi import Request
from pydantic import validate_email
from starlette_context import context


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
