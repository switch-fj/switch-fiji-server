from datetime import date, datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Column, Date, DateTime, Identity, Index, Integer, String
from sqlmodel import Field, Relationship, UniqueConstraint

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.batteries_soc.model import (
        BatterySOCConfigHistory,
        BatteryStateofCharge,
    )
    from app.modules.clients.model import Client
    from app.modules.contracts.model import Contract
    from app.modules.devices.model import Device
    from app.modules.mppt_function_check.model import SiteMPPTFunctionCheck
    from app.modules.panel_references.model import PanelReference
    from app.modules.pv_degradation.model import PvDegradation
    from app.modules.pv_summary.model import PVSummary
    from app.modules.string_wiring.model import StringWiring


class Site(MyAbstractSQLModel, table=True):
    """ORM model representing a physical installation site belonging to a client."""

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
    tz: Optional[str] = Field(
        default=None,
        sa_column_kwargs={"server_default": None},
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
    first_seen_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of first valid ESP32 data ingestion for this site.",
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"nullable": True},
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
    panel_refs: list["PanelReference"] = Relationship(back_populates="site")
    pv_summary: Optional["PVSummary"] = Relationship(back_populates="site")
    pv_degradation: Optional["PvDegradation"] = Relationship(back_populates="site")
    string_wiring: Optional["StringWiring"] = Relationship(back_populates="site")
    site_mppt_fn_check: list["SiteMPPTFunctionCheck"] = Relationship(back_populates="site")
    battery_soc_config: list["BatterySOCConfigHistory"] = Relationship(back_populates="site")
    battery_state_of_charge: list["BatteryStateofCharge"] = Relationship(back_populates="site")
    energy_usage: list["SiteEnergyUsage"] = Relationship(back_populates="site")


class SiteEnergyUsage(MyAbstractSQLModel, table=True):
    """
    Instantaneous energy usage snapshots for a site, sampled every 30 min
    across the full day (00:00-23:30).
    """

    __tablename__ = "site_energy_usage"
    __table_args__ = (
        UniqueConstraint(
            "site_uid",
            "date_at",
            "interval_in_minutes",
            name="uq_site_energy_usage",
        ),
        Index("ix_site_energy_usage_site_date", "site_uid", "date_at"),
    )

    site_uid: UUID = Field(foreign_key="sites.uid", nullable=False, index=True)
    date_at: date = Field(sa_column_kwargs={"nullable": False}, sa_type=Date)
    interval_in_minutes: int = Field(default=30)
    telemetry_reading_str: Optional[str] = Field(default=None)
    energy_usage_table_str: Optional[str] = Field(
        default=None, description="JSON-serialized instantaneous usage snapshots"
    )
    is_completed: bool = Field(default=False, index=True)

    site: "Site" = Relationship(back_populates="energy_usage")
