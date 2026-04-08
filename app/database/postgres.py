from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import Config
from app.core.logger import setup_logger

logger = setup_logger(__name__)

async_engine: AsyncEngine = create_async_engine(url=Config.DATABASE_URL)
AsyncSessionMaker = sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with async_engine.begin() as conn:
        try:
            logger.info("🔄 Connecting to Postgres...")
            await conn.run_sync(SQLModel.metadata.create_all, checkfirst=True)
            await conn.execute(text("SELECT 1"))
            logger.info("successfully connected to Postgres.")
        except ConnectionError as e:
            logger.error(f"Failed to connect to Postgres: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Postgres: {e}")
            raise


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionMaker() as async_session_maker:
        yield async_session_maker
