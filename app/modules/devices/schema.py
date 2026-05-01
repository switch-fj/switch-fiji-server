from enum import StrEnum


class DeviceType(StrEnum):
    """Enumeration of supported device categories."""

    METER = "meter"
    INVERTER = "inverter"
    AC_UNIT = "ac_unit"
    IRRADIANCE_METER = "irradiance_meter"


class MeterRoleEnum(StrEnum):
    """Enumeration of roles a meter device can fulfil at a site."""

    GEN_METER = "gen_meter"
    LOAD_METER = "load_meter"
    AUX_LOADS = "aux_loads"
    MICRO_INV = "micro_inv"
