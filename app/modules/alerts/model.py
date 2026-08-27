from sqlmodel import Field, UniqueConstraint

from app.shared.model import MyAbstractSQLModel


class AlertRule(MyAbstractSQLModel, table=True):
    """
    Defines a condition that, when met, should raise an alert.
    Evaluated on a schedule; matching entities get an Alert row.
    """

    __tablename__ = "alert_rules"
    __table_args__ = (UniqueConstraint("name", name="uq_alert_rules_name"),)

    name: str = Field(index=True)  # "device_offline", "site_offline", "mppt_channel_degraded", "battery_soc_low"
    entity_type: str  # "device" | "site"
    threshold_minutes: int  # how long the condition must hold before firing
    severity: str  # "warning" | "critical"
    is_active: bool = Field(default=True)
    config_str: str | None = Field(default=None, description="JSON-serialized rule-specific config")
