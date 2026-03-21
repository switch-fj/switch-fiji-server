from typing import Optional

from pydantic import EmailStr
from sqlalchemy import Boolean, Column, Identity, Integer, String
from sqlmodel import Field

from app.shared.model import MyAbstractSQLModel
from app.shared.schema import IdentityTypeEnum, UserRoleEnum


class User(MyAbstractSQLModel, table=True):
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

    @property
    def identity(self) -> int:
        return IdentityTypeEnum.USER.value
