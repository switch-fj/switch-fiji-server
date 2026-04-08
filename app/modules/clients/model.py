from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import EmailStr
from sqlalchemy import Boolean, Column, Identity, Integer, String
from sqlalchemy.orm import column_property
from sqlmodel import Field, Relationship, func, select

from app.shared.model import MyAbstractSQLModel
from app.shared.schema import IdentityTypeEnum

if TYPE_CHECKING:
    from app.modules.sites.model import Site
    from app.modules.users.model import User


class Client(MyAbstractSQLModel, table=True):
    __tablename__ = "clients"

    id: int = Field(
        sa_column=Column(
            Integer,
            Identity(always=True),
            unique=True,
            nullable=False,
        )
    )
    client_id: str = Field(
        description="external identifier, used for upsert conflict detection",
        sa_column=Column(
            String(255),
            unique=True,
            nullable=False,
        ),
    )
    client_name: str = Field(
        sa_column=Column(
            String(255),
            nullable=False,
        )
    )
    client_email: EmailStr = Field(sa_column=Column(String(320), index=True, unique=True, nullable=False))
    password_hash: Optional[str] = Field(sa_column=Column(String, nullable=True, default=None))
    is_email_verified: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            default=False,
            nullable=False,
        ),
    )
    user_uid: Optional[UUID] = Field(foreign_key="users.uid", default=None, nullable=True)

    @property
    def identity(self) -> int:
        return IdentityTypeEnum.CLIENT.value

    sites: list["Site"] = Relationship(back_populates="client")
    user: Optional["User"] = Relationship(
        back_populates="clients",
        sa_relationship_kwargs={"foreign_keys": "[Client.user_uid]"},
    )

    @classmethod
    def __declare_last__(cls):
        from app.modules.sites.model import Site

        cls.sites_count = column_property(
            select(func.count(Site.id)).where(Site.client_uid == cls.uid).correlate_except(Site).scalar_subquery()
        )
