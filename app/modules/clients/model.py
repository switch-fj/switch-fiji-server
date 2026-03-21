from typing import TYPE_CHECKING, Optional

from pydantic import EmailStr
from sqlalchemy import Boolean, Column, Identity, Integer, String
from sqlmodel import Field, Relationship

from app.shared.model import MyAbstractSQLModel
from app.shared.schema import IdentityTypeEnum

if TYPE_CHECKING:
    from app.modules.sites.model import Site


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

    @property
    def identity(self) -> int:
        return IdentityTypeEnum.CLIENT.value

    sites: list["Site"] = Relationship(back_populates="client")
