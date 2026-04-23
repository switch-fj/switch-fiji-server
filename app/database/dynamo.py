from typing import Optional

import aioboto3

from app.core.config import Config
from app.core.logger import setup_logger

logger = setup_logger(__name__)


class DynamoClient:
    _instance: Optional["DynamoClient"] = None
    _client = None
    _table = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init(self):
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
        async with self._client as dynamodb:
            return await dynamodb.Table(Config.AWS_TIME_SERIES_TABLE)

    async def close(self):
        if self._client:
            self._client = None
            logger.info("DynamoDB connection closed")


dynamo_client = DynamoClient()


async def init_dynamo() -> bool:
    try:
        logger.info("🔄 Connecting to DynamoDB...")
        await dynamo_client.init()
        return True
    except Exception as e:
        logger.error(f"❌ Unexpected DynamoDB error: {e}")
        logger.info("💡 Application will continue without DynamoDB features")
        return False
