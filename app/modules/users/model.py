from pydantic import EmailStr
from sqlalchemy import Boolean, Column, Identity, Integer, String
from sqlmodel import Field

from app.database.base_model import MyAbstractSQLModel


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
    password_hash: str = Field(sa_column=Column(String, nullable=False))
    is_email_verified: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            default=False,
            nullable=False,
        ),
    )
