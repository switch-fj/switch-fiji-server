from datetime import date, datetime, time
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlmodel import Date, DateTime, Field, Index, Relationship, Time, UniqueConstraint

from app.shared.model import MyAbstractSQLModel

if TYPE_CHECKING:
    from app.modules.sites.model import Site
    from app.modules.users.model import User


class BatterySOCConfigHistory(MyAbstractSQLModel, table=True):
    """
    Battery State of charge table for individual sites. Updated by telemetry data from dynamodb
    """

    __tablename__ = "battery_soc_config_history"

    site_uid: UUID = Field(foreign_key="sites.uid", nullable=False, index=True)
    user_uid: UUID = Field(foreign_key="users.uid", nullable=False, index=True)
    config_input_str: str = Field(description="JSON-serialized StringsInputItemModel")
    effective_from: datetime = Field(
        nullable=False,
        sa_type=DateTime(timezone=True),
    )
    effective_to: Optional[datetime] = Field(
        nullable=True,
        default=None,
        sa_column_kwargs={"nullable": True},
        sa_type=DateTime(timezone=True),
    )

    # Relationships
    site: "Site" = Relationship(back_populates="battery_soc_config")
    user: "User" = Relationship(back_populates="battery_soc_config")


class BatteryStateofCharge(MyAbstractSQLModel, table=True):
    __tablename__ = "battery_state_of_charge"
    __table_args__ = (
        UniqueConstraint(
            "site_uid",
            "date_at",
            "from_",
            "to",
            "interval_in_minutes",
            name="uq_battery_soc_check",
        ),
        Index("ix_site_battery_soc_site_date", "site_uid", "date_at"),
    )

    site_uid: UUID = Field(foreign_key="sites.uid", nullable=False, index=True)
    battery_soc_config_uid: UUID = Field(foreign_key="battery_soc_config_history.uid", nullable=False)
    date_at: date = Field(sa_column_kwargs={"nullable": False}, sa_type=Date)
    from_: time = Field(sa_type=Time)
    to: time = Field(sa_type=Time)
    interval_in_minutes: int = Field(default=30)
    telemetry_reading_str: Optional[str] = Field(default=None)
    battery_soc_table_str: Optional[str] = Field(description="JSON-serialized Battery state of charge")
    is_completed: bool = Field(default=False, index=True)

    site: "Site" = Relationship(back_populates="battery_state_of_charge")
    battery_soc_config_history: "BatterySOCConfigHistory" = Relationship()
