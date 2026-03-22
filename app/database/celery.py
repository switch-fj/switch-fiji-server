from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from core.config import Config


@asynccontextmanager
async def get_celery_db_session():
    engine = create_async_engine(Config.DATABASE_URL, pool_pre_ping=True)
    session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
    await engine.dispose()
