from typing import Optional

import aioboto3
import boto3

from app.core.config import Config
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class TimestreamConnection:
    """Singleton that manages both async (FastAPI) and sync (Celery) Timestream client access."""

    _instance: Optional["TimestreamConnection"] = None
    _session: Optional[aioboto3.Session] = None

    def __new__(cls):
        """Return the existing singleton instance or create one.

        Returns:
            The singleton TimestreamConnection instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init(self):
        """Create an aioboto3 session and verify connectivity with a test query.

        Returns:
            None

        Raises:
            Exception: If the Timestream connection or test query fails.
        """
        if self._session is None:
            try:
                logger.info("🔄 Connecting to Timestream...")
                self._session = aioboto3.Session(
                    aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                    region_name=Config.AWS_REGION,
                )
                async with self._session.client("timestream-query") as client:
                    await client.query(QueryString="SELECT 1")
                logger.info("✅ Timestream connection established successfully")
            except Exception as e:
                logger.error(f"❌ Failed to connect to Timestream: {e}")
                self._session = None
                raise

    async def get_async_client(self):
        """Async context manager — for FastAPI."""
        if not self._session:
            raise RuntimeError("Timestream not initialized. Call init() first.")
        return self._session.client("timestream-query")

    def get_sync_client(self):
        """Sync boto3 client — for Celery workers."""
        return boto3.client(
            "timestream-query",
            region_name=Config.AWS_REGION,
            aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
        )

    async def close(self):
        """Release the aioboto3 session reference.

        Returns:
            None
        """
        if self._session:
            self._session = None
            logger.info("Timestream connection closed")


timestream_connection = TimestreamConnection()


async def init_timestream() -> bool:
    """Initialise the global Timestream connection on application startup.

    Returns:
        True if the connection was established successfully, False otherwise.
    """
    try:
        await timestream_connection.init()
        return True
    except Exception as e:
        logger.error(f"❌ Unexpected Timestream error: {e}")
        logger.info("💡 Application will continue without Timestream features")
        return False
