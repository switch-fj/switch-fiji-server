from enum import StrEnum


class AlertRuleName(StrEnum):
    DEVICE_OFFLINE = "Device offline"
    SITE_OFFLINE = "Site offline"
    MPPT_CHANNEL_DEGRADED = "MPPT Channel degraded"
    BATTERY_SOC_LOW = "Low Battery SOC"


class AlertEnitityType(StrEnum):
    DEVICE = "device"
    SITE = "site"


class AlertRuleSeverity(StrEnum):
    WARNING = "warning"
    CRITICAL = "CRITICAL"
