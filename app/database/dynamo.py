from typing import Optional

import aioboto3

from app.core.config import Config
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class DynamoClient:
    """Singleton async DynamoDB client used by FastAPI request handlers."""

    _instance: Optional["DynamoClient"] = None
    _client = None
    _table = None

    def __new__(cls):
        """Return the existing singleton instance or create one.

        Returns:
            The singleton DynamoClient instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init(self):
        """Establish an async DynamoDB session using AWS credentials from config.

        Returns:
            None

        Raises:
            Exception: If the aioboto3 session cannot be created.
        """
        if self._client is None:
            try:
                session = aioboto3.Session(
                    aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                    region_name=Config.AWS_REGION,
                )
                self._client = session.resource("dynamodb")
                logger.info("✅ DynamoDB connection established successfully")
            except Exception as e:
                logger.error(f"❌ Failed to connect to DynamoDB: {e}")
                self._client = None
                raise

    async def _get_table(self):
        """Open the DynamoDB resource context and return the configured time-series table.

        Returns:
            The aioboto3 DynamoDB Table resource for AWS_TIME_SERIES_TABLE.
        """
        async with self._client as dynamodb:
            return await dynamodb.Table(Config.AWS_TIME_SERIES_TABLE)

    async def close(self):
        """Release the DynamoDB session reference.

        Returns:
            None
        """
        if self._client:
            self._client = None
            logger.info("DynamoDB connection closed")


dynamo_client = DynamoClient()


async def init_dynamo() -> bool:
    """Initialise the global DynamoDB client on application startup.

    Returns:
        True if the connection was established successfully, False otherwise.
    """
    try:
        logger.info("🔄 Connecting to DynamoDB...")
        await dynamo_client.init()
        return True
    except Exception as e:
        logger.error(f"❌ Unexpected DynamoDB error: {e}")
        logger.info("💡 Application will continue without DynamoDB features")
        return False
