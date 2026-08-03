from decimal import Decimal

from pydantic import BaseModel


class DeviceGatewayModel(BaseModel):
    firmware: str
    gateway_id: str


class DeviceClientModel(BaseModel):
    client_email: str
    site_id: Decimal
    client_name: str
    client_id: Decimal


class DeviceTimestampModel(BaseModel):
    ts_epoch_ms: Decimal


class DeviceMeterModel(BaseModel):
    kwh_export: Decimal
    kw1: Decimal
    kwh_import: Decimal
    kw3: Decimal
    kw2: Decimal
    description: str
    pf_total: Decimal
    kvar2: Decimal
    kvarh_export: Decimal
    kvar3: Decimal
    kvar1: Decimal
    kva_total: Decimal
    kvah_total: str
    kw_total: Decimal
    i1: Decimal
    kvar_total: Decimal
    i2: Decimal
    kva1: Decimal
    i3: Decimal
    kva2: Decimal
    kva3: Decimal
    freq_hz: Decimal
    pf1: Decimal
    v1: Decimal
    kvarh_import: Decimal
    v2: Decimal
    pf3: Decimal
    v3: Decimal
    pf2: Decimal
    slave_id: Decimal
