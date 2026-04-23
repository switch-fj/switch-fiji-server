from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Column, Identity, Integer
from sqlmodel import Field, Relationship, UniqueConstraint

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.sites.model import Site


class Device(MyAbstractSQLModel, table=True):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("site_uid", "slave_id", "device_type", name="uq_site_slave_device_type"),)

    id: int = Field(
        sa_column=Column(
            Integer,
            Identity(always=True),
            unique=True,
            nullable=False,
        )
    )
    site_uid: UUID = Field(foreign_key="sites.uid", nullable=False)
    slave_id: int = Field(
        description="external identifier, scoped to a site + device_type",
        nullable=False,
    )
    device_type: str = Field(nullable=False)
    meter_role: Optional[str] = Field(
        default=None,
        nullable=True,
        description="Only applies when device_type is 'meter'. e.g. gen_meter, load_meter, aux_loads, micro_inv",
    )
    is_dual_tariff: Optional[bool] = Field(
        default=None,
        nullable=True,
        description="Only applies when device_type is 'meter'. Derived from firmware isDualTariff()",
    )

    site: "Site" = Relationship(
        back_populates="devices",
        sa_relationship_kwargs={"foreign_keys": "Device.site_uid"},
    )
