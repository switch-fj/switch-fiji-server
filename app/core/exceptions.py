from typing import Callable, Optional, Union, get_args, get_origin

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """The base class for handling exceptions around the app."""

    def __init__(self, message: Optional[str] = None):
        """Initialise the exception with an optional custom message.

        Args:
            message: Human-readable error message. Subclasses provide a default.
        """
        self.message = message
        super().__init__(message)


class InvalidToken(AppException):
    """This handles user invalid token exceptions"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default invalid-token message.

        Args:
            message: Override message. Defaults to a standard invalid token description.
        """
        super().__init__(message or "This token is invalid or expired. Pls get a new token.")


class ResourceExists(AppException):
    """Raised when a required resource already exists in database"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default resource-exists message.

        Args:
            message: Override message. Defaults to "Resource already exists."
        """
        super().__init__(message or "Resource already exists.")


class NotFound(AppException):
    """Raised when a required resource doesn't exist in database"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default not-found message.

        Args:
            message: Override message. Defaults to "Resource doesn't exist."
        """
        super().__init__(message or "Resource doesn't exist.")


class Forbidden(AppException):
    """Raised when a required resource is been accessed by unathorized users."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default forbidden message.

        Args:
            message: Override message. Defaults to an access-denied description.
        """
        super().__init__(message or "You do not have access to this resource.")


class InActive(AppException):
    """Raised when a required resource is inactive in the database"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default inactive-resource message.

        Args:
            message: Override message. Defaults to "Resource is inactive."
        """
        super().__init__(message or "Resource is inactive.")


class UserEmailExists(AppException):
    """This handles user email exists"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default duplicate-email message.

        Args:
            message: Override message. Defaults to "User with email already exist."
        """
        super().__init__(message or "User with email already exist.")


class WrongCredentials(AppException):
    """This handles wrong user email or password."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default wrong-credentials message.

        Args:
            message: Override message. Defaults to "Wrong email or password."
        """
        super().__init__(message or "Wrong email or password.")


class TokenExpired(AppException):
    """This handles expired user token."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default token-expired message.

        Args:
            message: Override message. Defaults to "Token has expired."
        """
        super().__init__(message or "Token has expired.")


class AccessTokenRequired(AppException):
    """This handles expired user token."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default access-token-required message.

        Args:
            message: Override message. Defaults to "Provide an access token."
        """
        super().__init__(message or "Provide an access token.")


class RefreshTokenRequired(AppException):
    """This handles expired user token."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default refresh-token-required message.

        Args:
            message: Override message. Defaults to "Provide a refresh token."
        """
        super().__init__(message or "Provide a refresh token.")


class RefreshTokenExpired(AppException):
    """This handles expired user token."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default refresh-token-expired message.

        Args:
            message: Override message. Defaults to error code "E402".
        """
        super().__init__(message or "E402")


class ExpiredLink(AppException):
    """This handles expired password reset token"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default expired-link message.

        Args:
            message: Override message. Defaults to "Link expired. get a new one."
        """
        super().__init__(message or "Link expired. get a new one.")


class InvalidLink(AppException):
    """This handles invalid password reset token"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default invalid-link message.

        Args:
            message: Override message. Defaults to "Link is invalid. get a new one."
        """
        super().__init__(message or "Link is invalid. get a new one.")


class InvalidOTP(AppException):
    """This handles invalid otp"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default invalid-OTP message.

        Args:
            message: Override message. Defaults to "OTP is invalid. get a new one."
        """
        super().__init__(message or "OTP is invalid. get a new one.")


class InsufficientPermissions(Exception):
    """Raised when user doesn't have required role/permissions"""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default insufficient-permissions message.

        Args:
            message: Override message. Defaults to an access-denied description.
        """
        self.message = message or "You don't have permission to access this resource."
        super().__init__(self.message)


class BadRequest(AppException):
    """Raised when a bad request is made to the api."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default bad-request message.

        Args:
            message: Override message. Defaults to "Bad request".
        """
        self.message = message or "Bad request"
        super().__init__(self.message)


class TooManyRequest(AppException):
    """Raised when a too many requests are made to the api."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default too-many-requests message.

        Args:
            message: Override message. Defaults to "Too many request".
        """
        self.message = message or "Too many request"
        super().__init__(self.message)


class TooManyAttempts(AppException):
    """Raised when a too many attempts are made to the api."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default too-many-attempts message.

        Args:
            message: Override message. Defaults to "Too many attempts".
        """
        self.message = message or "Too many attempts"
        super().__init__(self.message)


class UserNotVerified(AppException):
    """Raised when an unverified user calls an endpoint."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default unverified-user message.

        Args:
            message: Override message. Defaults to "Your email is not verified."
        """
        self.message = message or "Your email is not verified."
        super().__init__(self.message)


class SameNewOldPassword(AppException):
    """Raised when old password is same as new password."""

    def __init__(self, message: Optional[str] = None):
        """Initialise with a default same-password message.

        Args:
            message: Override message. Defaults to a same-password description.
        """
        self.message = message or "New password cannot be same as old password."
        super().__init__(self.message)


def create_exception_handler(
    status_code: int, default_message: str = "An error occurred"
) -> Callable[[Request, Exception], JSONResponse]:
    """Create a reusable FastAPI exception handler that returns a structured JSON error response.

    Args:
        status_code: HTTP status code to return in the response.
        default_message: Fallback message used when the exception carries no message.

    Returns:
        An async exception handler function compatible with FastAPI's add_exception_handler.
    """

    async def exception_handler(req: Request, exc: AppException) -> JSONResponse:
        message = getattr(exc, "message", None) or default_message

        return JSONResponse(
            status_code=status_code,
            content={"error_code": exc.__class__.__name__, "message": message},
        )

    return exception_handler


def get_model_from_request(request: Request):
    """Extract the Pydantic body model type from a FastAPI request's route definition.

    Args:
        request: The incoming FastAPI request object.

    Returns:
        The Pydantic model class of the route's body field, or None if unavailable.
    """
    try:
        return request.scope["route"].body_field.type_
    except Exception:
        return None


def get_field_title(model, field_name: str) -> str | None:
    """Retrieve the declared title of a Pydantic model field.

    Args:
        model: The Pydantic model class to inspect.
        field_name: The name of the field whose title to retrieve.

    Returns:
        The field's title string, or None if the model or field is not found.
    """
    if not model or not hasattr(model, "model_fields"):
        return None

    field = model.model_fields.get(field_name)
    if not field:
        return None

    return field.title


def prettify(name: str) -> str:
    """Convert a snake_case field name into a capitalised human-readable label.

    Args:
        name: The snake_case string to convert.

    Returns:
        A string with underscores replaced by spaces and the first letter capitalised.
    """
    return name.replace("_", " ").capitalize()


def format_error_message(label: str, err: dict) -> str:
    """Format a single Pydantic validation error into a human-readable string.

    Args:
        label: The human-readable field label to use in the message.
        err: The Pydantic error dictionary containing 'type' and 'msg' keys.

    Returns:
        A formatted error message string.
    """
    error_type = err.get("type")

    if error_type == "missing":
        return f"{label} is required"

    return f"{label}: {err.get('msg')}"


def unwrap_type(annotation):
    """Unwrap a generic type annotation to its inner type.

    Handles list, tuple, dict, and Optional (Union with None) generics.

    Args:
        annotation: A Python type annotation to unwrap.

    Returns:
        The innermost concrete type, or the original annotation if no unwrapping applies.
    """
    origin = get_origin(annotation)

    if origin is None:
        return annotation

    if origin is list:
        return get_args(annotation)[0]

    if origin is tuple:
        return get_args(annotation)[0]

    if origin is dict:
        return get_args(annotation)[1]

    if origin is Union:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        return args[0] if args else annotation

    return annotation


def resolve_field(model, loc: list):
    """Walk a nested field location path through a chain of Pydantic models.

    Args:
        model: The root Pydantic model class to start traversal from.
        loc: A list of field name strings (and optional integer indices) representing the path.

    Returns:
        A tuple of (field_info, resolved_model) for the deepest field, or (None, None) if not found.
    """
    current_model = model
    field_info = None

    for part in loc:
        if isinstance(part, int):
            continue

        if not hasattr(current_model, "model_fields"):
            return None, None

        field_info = current_model.model_fields.get(part)
        if not field_info:
            return None, None

        annotation = unwrap_type(field_info.annotation)
        current_model = annotation

    return field_info, current_model


def get_label(model, loc: list) -> str:
    """Determine the human-readable label for a field given its location path.

    Uses the field's declared title if available, otherwise prettifies the field name.

    Args:
        model: The root Pydantic model class.
        loc: A list of field name strings representing the path to the field.

    Returns:
        The field's title, a prettified field name, or "Field" as a fallback.
    """
    field_name = loc[-1] if loc else None

    field_info, _ = resolve_field(model, loc)

    if field_info and field_info.title:
        return field_info.title

    if field_name:
        return prettify(field_name)

    return "Field"


def register_exceptions(app: FastAPI):
    """Register all application exception handlers on the FastAPI instance.

    Args:
        app: The FastAPI application instance to attach exception handlers to.

    Returns:
        None
    """
    app.add_exception_handler(InvalidToken, create_exception_handler(status.HTTP_401_UNAUTHORIZED))
    app.add_exception_handler(NotFound, create_exception_handler(status.HTTP_404_NOT_FOUND))
    app.add_exception_handler(InActive, create_exception_handler(status.HTTP_404_NOT_FOUND))
    app.add_exception_handler(ResourceExists, create_exception_handler(status.HTTP_409_CONFLICT))
    app.add_exception_handler(WrongCredentials, create_exception_handler(status.HTTP_404_NOT_FOUND))
    app.add_exception_handler(UserEmailExists, create_exception_handler(status.HTTP_409_CONFLICT))
    app.add_exception_handler(AccessTokenRequired, create_exception_handler(status.HTTP_401_UNAUTHORIZED))
    app.add_exception_handler(RefreshTokenRequired, create_exception_handler(status.HTTP_410_GONE))
    app.add_exception_handler(RefreshTokenExpired, create_exception_handler(status.HTTP_410_GONE))
    app.add_exception_handler(TokenExpired, create_exception_handler(status.HTTP_401_UNAUTHORIZED))
    app.add_exception_handler(ExpiredLink, create_exception_handler(status.HTTP_410_GONE))
    app.add_exception_handler(InvalidLink, create_exception_handler(status.HTTP_410_GONE))
    app.add_exception_handler(InvalidOTP, create_exception_handler(status.HTTP_410_GONE))
    app.add_exception_handler(
        InsufficientPermissions,
        create_exception_handler(status.HTTP_405_METHOD_NOT_ALLOWED),
    )
    app.add_exception_handler(BadRequest, create_exception_handler(status.HTTP_400_BAD_REQUEST))
    app.add_exception_handler(TooManyRequest, create_exception_handler(status.HTTP_400_BAD_REQUEST))
    app.add_exception_handler(TooManyAttempts, create_exception_handler(status.HTTP_400_BAD_REQUEST))
    app.add_exception_handler(UserNotVerified, create_exception_handler(status.HTTP_403_FORBIDDEN))
    app.add_exception_handler(Forbidden, create_exception_handler(status.HTTP_403_FORBIDDEN))
    app.add_exception_handler(SameNewOldPassword, create_exception_handler(status.HTTP_403_FORBIDDEN))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Format Pydantic validation errors into a single human-readable JSON response.

        Args:
            request: The incoming request that triggered validation.
            exc: The RequestValidationError containing one or more field errors.

        Returns:
            A JSONResponse with HTTP 400 and a combined error message.
        """
        model = get_model_from_request(request)

        messages = []

        for err in exc.errors():
            loc = [x for x in err.get("loc", []) if x != "body"]
            field_name = loc[-1] if loc else None

            title = get_field_title(model, field_name) if field_name else None
            label = title if title else get_label(model, loc)
            messages.append(format_error_message(label, err))

        combined_message = ", ".join(messages)

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error_code": "BadRequest",
                "message": combined_message,
            },
        )

    @app.exception_handler(status.HTTP_500_INTERNAL_SERVER_ERROR)
    async def internal_server_error(request: Request, exc):
        """Return a generic JSON response for unhandled 500 errors.

        Args:
            request: The incoming request that triggered the error.
            exc: The unhandled exception.

        Returns:
            A JSONResponse with HTTP 500 and a generic error message.
        """
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "message": "A 500 error exception occurred!",
                "error_code": "InternalServerError",
            },
        )
