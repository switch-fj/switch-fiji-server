from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import EmailStr
from sqlalchemy import Boolean, Column, Identity, Integer, String
from sqlmodel import Field, Relationship

from app.shared.model import MyAbstractSQLModel
from app.shared.schema import IdentityTypeEnum, UserRoleEnum

if TYPE_CHECKING:
    from app.modules.clients.model import Client


class User(MyAbstractSQLModel, table=True):
    """ORM model representing an internal platform user (admin or engineer)."""

    __tablename__ = "users"
    id: int = Field(
        sa_column=Column(
            Integer,
            Identity(always=True),
            unique=True,
            nullable=False,
        )
    )
    email: EmailStr = Field(sa_column=Column(String(320), index=True, unique=True, nullable=False))
    password_hash: Optional[str] = Field(sa_column=Column(String, nullable=True, default=None))
    is_email_verified: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            default=False,
            nullable=False,
        ),
    )
    role: UserRoleEnum = Field(
        default=UserRoleEnum.ENGINEER.value,
        sa_column=Column(
            Integer,
            nullable=False,
            default=UserRoleEnum.ENGINEER.value,
        ),
    )
    registrar_uid: Optional[UUID] = Field(foreign_key="users.uid", nullable=True, default=None)

    @property
    def identity(self) -> int:
        """Return the identity type enum value for JWT claims.

        Returns:
            The integer value of IdentityTypeEnum.USER.
        """
        return IdentityTypeEnum.USER.value

    clients: list["Client"] = Relationship(back_populates="user")
    registrar: Optional["User"] = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[User.registrar_uid]",
            "remote_side": "[User.uid]",
        }
    )
