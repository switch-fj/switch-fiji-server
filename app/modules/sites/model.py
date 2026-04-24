from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Column, Identity, Integer, String
from sqlmodel import Field, Relationship, UniqueConstraint

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.clients.model import Client
    from app.modules.contracts.model import Contract
    from app.modules.devices.model import Device


class Site(MyAbstractSQLModel, table=True):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("client_uid", "site_id", name="uq_client_site"),)

    id: int = Field(
        sa_column=Column(
            Integer,
            Identity(always=True),
            unique=True,
            nullable=False,
        )
    )
    client_uid: UUID = Field(foreign_key="clients.uid", index=True, nullable=False)
    site_id: str = Field(
        description="external identifier, scoped to a client",
        sa_column=Column(
            String(255),
            nullable=True,
        ),
    )
    site_name: Optional[str] = Field(
        sa_column=Column(
            String(255),
            default=None,
            nullable=True,
        )
    )
    gateway_id: str = Field(
        sa_column=Column(
            String(255),
            default=None,
            nullable=True,
        )
    )
    firmware: Optional[str] = Field(
        sa_column=Column(
            String(255),
            default=None,
            nullable=True,
        )
    )

    # Relationships
    client: "Client" = Relationship(
        back_populates="sites",
        sa_relationship_kwargs={"foreign_keys": "Site.client_uid"},
    )
    devices: list["Device"] = Relationship(back_populates="site")
    contract: Optional["Contract"] = Relationship(
        back_populates="site",
        sa_relationship_kwargs={"foreign_keys": "[Contract.site_uid]"},
    )
