from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = "development"

    # general
    API_DOMAIN: str = "http://localhost:8000"
    STAGING_API_DOMAIN: str
    FRONTEND_URL: str

    # auth
    JWT_SECRET: str
    JWT_ALGORITHM: str
    DEFAULT_ADMIN_EMAIL: str
    DEFAULT_ADMIN_PASS: str

    # database
    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_SSL: bool = False
    REMOTE_DB_URL: str = ""

    # redis
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: Optional[str] = None

    # email
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int = 587
    MAIL_SERVER: str
    MAIL_FROM_NAME: str
    MAIL_STARTTLS: bool = False
    MAIL_SSL_TLS: bool = True
    EMAIL_SALT: str

    # resend
    USE_RESEND: bool
    RESEND_API_KEY: str

    # app
    DEFAULT_PAGE_MIN_LIMIT: int = 10
    DEFAULT_PAGE_MAX_LIMIT: int = 100
    DEFAULT_PAGE_LIMIT: int = 30
    DEFAULT_PAGE_OFFSET: int = 0
    CURSOR_SECRET: str

    USE_REMOTE_DB: bool = False

    # aws
    AWS_REGION: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_TIME_SERIES_TABLE: str = ""

    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"

    @property
    def DATABASE_URL(self) -> str:
        password = quote_plus(self.DB_PASSWORD)
        url = f"postgresql+asyncpg://{self.DB_USER}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

        return self.REMOTE_DB_URL if self.USE_REMOTE_DB else url

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings():
    return Settings()


Config = get_settings()
