from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Config
from app.core.logger import setup_logger

logger = setup_logger(__name__)

async_engine: AsyncEngine = create_async_engine(
    url=Config.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=False,
)
AsyncSessionMaker = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Test the database connection by executing a simple query on startup.

    Returns:
        None

    Raises:
        ConnectionError: If a connection error occurs when reaching Postgres.
        Exception: For any other unexpected error during connection.
    """
    async with async_engine.begin() as conn:
        try:
            logger.info("🔄 Connecting to Postgres...")
            await conn.execute(text("SELECT 1"))
            logger.info("successfully connected to Postgres.")
        except ConnectionError as e:
            logger.error(f"Failed to connect to Postgres: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Postgres: {e}")
            raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Yields:
        An AsyncSession instance bound to the application's async engine.
    """
    async with AsyncSessionMaker() as async_session_maker:
        yield async_session_maker
