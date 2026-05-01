from functools import lru_cache
from typing import Optional
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # app
    ENV: str = "development"
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    ALLOW_LOCAL_FRONTEND: bool
    USE_REMOTE_DB: bool = False
    DEFAULT_PAGE_MIN_LIMIT: int = 10
    DEFAULT_PAGE_MAX_LIMIT: int = 100
    DEFAULT_PAGE_LIMIT: int = 30
    DEFAULT_PAGE_OFFSET: int = 0
    CURSOR_SECRET: str

    # general
    API_DOMAIN: Optional[str] = ""
    STAGING_API_DOMAIN: Optional[str] = None
    FRONTEND_URL: Optional[str] = "http://localhost:3000"

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
    USE_RESEND: bool = False
    RESEND_API_KEY: str

    # aws - access
    AWS_REGION: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # aws - dynamoDB
    AWS_TIME_SERIES_TABLE: str = ""

    # aws - s3 bucket
    AWS_S3_BUCKET: str = ""

    # aws - timestream
    AWS_TIMESTREAM_DATABASE: str = ""
    AWS_TIMESTREAM_TABLE: str = ""

    @property
    def is_relaxed_cookie_env(self) -> bool:
        """Return True when running in development or with local frontend enabled.

        Returns:
            True if the environment is development or ALLOW_LOCAL_FRONTEND is set.
        """
        return self.ENV == "development" or self.ALLOW_LOCAL_FRONTEND

    @property
    def DATABASE_URL(self) -> str:
        """Build the async PostgreSQL connection URL.

        Returns:
            The asyncpg database URL, using the remote URL when USE_REMOTE_DB is True.
        """
        password = quote_plus(self.DB_PASSWORD)
        url = f"postgresql+asyncpg://{self.DB_USER}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

        return self.REMOTE_DB_URL if self.USE_REMOTE_DB else url

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Build the synchronous PostgreSQL connection URL for Celery workers.

        Returns:
            The psycopg2 database URL, using the remote URL (with asyncpg replaced) when USE_REMOTE_DB is True.
        """
        password = quote_plus(self.DB_PASSWORD)
        url = f"postgresql+psycopg2://{self.DB_USER}:{password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

        return self.REMOTE_DB_URL.replace("asyncpg", "psycopg2") if self.USE_REMOTE_DB else url

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings():
    """Instantiate and cache the Settings object.

    Returns:
        A cached Settings instance loaded from the environment.
    """
    return Settings()


Config = get_settings()
