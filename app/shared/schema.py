from datetime import datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import Annotated, Generic, Optional, TypeVar, Union
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.utils import email_validator, uuid_serializer

T = TypeVar("T")

TwoDP = Annotated[Decimal, Field(decimal_places=2, max_digits=10)]


class UserRoleEnum(IntEnum):
    """Internal staff roles — controls what they can do on the platform."""

    ADMIN = 1
    ENGINEER = 2


class IdentityTypeEnum(IntEnum):
    """
    Used in JWT claims to distinguish token type.
    Not stored in any table — only lives in the token payload.
    """

    USER = 1
    CLIENT = 2


class PasscodeEnum(StrEnum):
    LOGIN = "login"


class AuthType(StrEnum):
    OTP = "otp"
    PWD = "pwd"


class DBModel(BaseModel):
    uid: UUID
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_dt(self, value: datetime):
        if value:
            return value.isoformat()

    @field_serializer("uid")
    def serialize_uuid(self, value: UUID):
        return uuid_serializer(value)

    model_config = ConfigDict(from_attributes=True)


class TokenIdentityModel(BaseModel):
    id: int
    uid: str
    email: str
    identity: int
    role: Optional[int]
    is_email_verified: bool

    model_config = ConfigDict(from_attributes=True)


class ServerRespModel(BaseModel, Generic[T]):
    data: T
    message: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class OffsetPaginationModel(BaseModel):
    total: int
    current_page: int
    limit: int
    total_pages: int


class CursorPaginationModel(BaseModel):
    limit: int
    next_cursor: Optional[str]
    prev_cursor: Optional[str]


P = TypeVar("P", bound=Union[OffsetPaginationModel, CursorPaginationModel])


class PaginatedRespModel(BaseModel, Generic[T, P]):
    items: list[T]
    pagination: P


class EmailModel(BaseModel):
    email: str = Field(...)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value):
        return email_validator(value)


class UpdateIdentityPwdModel(BaseModel):
    password: str = Field(...)


class SetPwdModel(EmailModel):
    new_password: str


class ChangePwdModel(BaseModel):
    old_password: str
    new_password: str


class TokenModel(BaseModel):
    access_token: str
    is_email_verified: bool
    auth_type: AuthType


class ResetPwdModel(BaseModel):
    token: str
    new_password: str


class IdentityLoginModel(EmailModel):
    password: Optional[str] = Field(default=None)


class VerifyLoginModel(EmailModel):
    otp: str = Field(...)


class HTMLContent:
    def __init__(self, _subject: str, _template: str):
        self.subject = _subject
        self.template = _template


class MailTypes:
    EMAIL_VERIFICATION = HTMLContent("Verify your account", "email_verification.html")
    PWD_RESET = HTMLContent("Password reset", "pwd_reset.html")
    VERIFY_LOGIN = HTMLContent("Verify Login Request", "verify_login.html")


class MailModel(BaseModel):
    subject: str
    reciepients: list[str]
    payload: dict
    template: str
    attachments: list[UploadFile] = ([],)


class UserResponseModel(DBModel):
    email: str
    role: Optional[int]
    identity: int
    is_email_verified: bool

    model_config = ConfigDict(from_attributes=True)


class CurrencyEnum(StrEnum):
    AED = "AED"
    AFN = "AFN"
    ALL = "ALL"
    AMD = "AMD"
    ANG = "ANG"
    AOA = "AOA"
    ARS = "ARS"
    AUD = "AUD"
    AWG = "AWG"
    AZN = "AZN"
    BAM = "BAM"
    BBD = "BBD"
    BDT = "BDT"
    BGN = "BGN"
    BHD = "BHD"
    BIF = "BIF"
    BMD = "BMD"
    BND = "BND"
    BOB = "BOB"
    BRL = "BRL"
    BSD = "BSD"
    BTN = "BTN"
    BWP = "BWP"
    BYN = "BYN"
    BZD = "BZD"
    CAD = "CAD"
    CDF = "CDF"
    CHF = "CHF"
    CLP = "CLP"
    CNY = "CNY"
    COP = "COP"
    CRC = "CRC"
    CUP = "CUP"
    CVE = "CVE"
    CZK = "CZK"
    DJF = "DJF"
    DKK = "DKK"
    DOP = "DOP"
    DZD = "DZD"
    EGP = "EGP"
    ERN = "ERN"
    ETB = "ETB"
    EUR = "EUR"
    FJD = "FJD"
    FKP = "FKP"
    GBP = "GBP"
    GEL = "GEL"
    GHS = "GHS"
    GIP = "GIP"
    GMD = "GMD"
    GNF = "GNF"
    GTQ = "GTQ"
    GYD = "GYD"
    HKD = "HKD"
    HNL = "HNL"
    HRK = "HRK"
    HTG = "HTG"
    HUF = "HUF"
    IDR = "IDR"
    ILS = "ILS"
    INR = "INR"
    IQD = "IQD"
    IRR = "IRR"
    ISK = "ISK"
    JMD = "JMD"
    JOD = "JOD"
    JPY = "JPY"
    KES = "KES"
    KGS = "KGS"
    KHR = "KHR"
    KMF = "KMF"
    KPW = "KPW"
    KRW = "KRW"
    KWD = "KWD"
    KYD = "KYD"
    KZT = "KZT"
    LAK = "LAK"
    LBP = "LBP"
    LKR = "LKR"
    LRD = "LRD"
    LSL = "LSL"
    LYD = "LYD"
    MAD = "MAD"
    MDL = "MDL"
    MGA = "MGA"
    MKD = "MKD"
    MMK = "MMK"
    MNT = "MNT"
    MOP = "MOP"
    MRU = "MRU"
    MUR = "MUR"
    MVR = "MVR"
    MWK = "MWK"
    MXN = "MXN"
    MYR = "MYR"
    MZN = "MZN"
    NAD = "NAD"
    NGN = "NGN"
    NIO = "NIO"
    NOK = "NOK"
    NPR = "NPR"
    NZD = "NZD"
    OMR = "OMR"
    PAB = "PAB"
    PEN = "PEN"
    PGK = "PGK"
    PHP = "PHP"
    PKR = "PKR"
    PLN = "PLN"
    PYG = "PYG"
    QAR = "QAR"
    RON = "RON"
    RSD = "RSD"
    RUB = "RUB"
    RWF = "RWF"
    SAR = "SAR"
    SBD = "SBD"
    SCR = "SCR"
    SDG = "SDG"
    SEK = "SEK"
    SGD = "SGD"
    SHP = "SHP"
    SLE = "SLE"
    SLL = "SLL"
    SOS = "SOS"
    SRD = "SRD"
    SSP = "SSP"
    STN = "STN"
    SVC = "SVC"
    SYP = "SYP"
    SZL = "SZL"
    THB = "THB"
    TJS = "TJS"
    TMT = "TMT"
    TND = "TND"
    TOP = "TOP"
    TRY = "TRY"
    TTD = "TTD"
    TWD = "TWD"
    TZS = "TZS"
    UAH = "UAH"
    UGX = "UGX"
    USD = "USD"
    UYU = "UYU"
    UZS = "UZS"
    VES = "VES"
    VND = "VND"
    VUV = "VUV"
    WST = "WST"
    XAF = "XAF"
    XCD = "XCD"
    XOF = "XOF"
    XPF = "XPF"
    YER = "YER"
    ZAR = "ZAR"
    ZMW = "ZMW"
    ZWL = "ZWL"
