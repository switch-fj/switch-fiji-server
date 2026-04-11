from typing import Optional

import backoff
import redis as syncredis
import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, RedisError

from app.core.config import Config
from app.core.logger import setup_logger
from app.utils import build_redis_url

logger = setup_logger(__name__)


class AsyncRedisClient:
    _instance: Optional["AsyncRedisClient"] = None
    _client: Optional[aioredis.Redis] = None
    BLOCKLIST_PREFIX = "blocked:"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def init(self):
        """Initialize Redis connection with retries"""
        if self._client is None:
            try:
                retry = Retry(ExponentialBackoff(), 3)
                self._client = aioredis.from_url(
                    url=build_redis_url(),
                    retry=retry,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    health_check_interval=30,
                )
                # Test connection
                await self._client.ping()
                logger.info("Successfully connected to Redis")
            except ConnectionError as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._client = None
                raise
            except Exception as e:
                logger.error(f"Unexpected error connecting to Redis: {e}")
                self._client = None
                raise

    @property
    def client(self) -> Optional[aioredis.Redis]:
        return self._client

    async def close(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    @backoff.on_exception(backoff.expo, (ConnectionError, RedisError), max_tries=3, max_time=30)
    async def add_to_blocklist(self, key: str, expiry: int = 86400) -> bool:
        """Add token to blocklist with retry mechanism"""
        if not self._client:
            logger.warning("Redis client not initialized")
            return False

        try:
            await self._client.set(name=f"{self.BLOCKLIST_PREFIX}:{key}", value=key, ex=expiry)
            return True
        except Exception as e:
            logger.error(f"Error adding to blocklist: {e}")
            raise

    async def in_blocklist(self, key: str) -> bool:
        """Check if token is in blocklist"""
        if not self._client:
            logger.warning("Redis client not initialized")
            return False

        try:
            return await self._client.exists(f"{self.BLOCKLIST_PREFIX}:{key}") > 0
        except Exception as e:
            logger.error(f"Error checking blocklist: {e}")
            return False


class SyncRedisClient:
    _instance: Optional["SyncRedisClient"] = None
    _client: Optional[syncredis.Redis] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init(self):
        if self._client is None:
            try:
                self._client = syncredis.from_url(
                    url=build_redis_url(),
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
                self._client.ping()
                logger.info("✅ Sync Redis connection established")
            except Exception as e:
                logger.error(f"Failed to connect to sync Redis: {e}")
                self._client = None
                raise

    def set_site_stats(self, site_uid: str, stats: str, ttl: int = 600) -> bool:
        """
        Write computed site stats to Redis.
        Called by Celery worker after computing the 4 variables.
        stats is a JSON string.
        TTL default 600s = 10 mins (2x the ESP push interval).
        """
        if not self._client:
            logger.warning("Sync Redis client not initialized")
            return False
        try:
            self._client.setex(
                name=f"site_stats:{site_uid}",
                time=ttl,
                value=stats,
            )
            return True
        except Exception as e:
            logger.error(f"Error writing site stats to Redis: {e}")
            return False

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
            logger.info("Sync Redis connection closed")


async_redis_client = AsyncRedisClient()
sync_redis_client = SyncRedisClient()


async def init_async_redis() -> bool:
    """Initialize Redis connection with detailed status logging"""
    try:
        logger.info(f"🔄 Connecting to Redis at {Config.REDIS_HOST}:{Config.REDIS_PORT}...")
        await async_redis_client.init()

        # Verify connection with PING
        if await async_redis_client.client.ping():
            logger.info("✅ Redis connection established successfully")

            # Log Redis server info
            info = await async_redis_client.client.info()
            logger.info(f"📊 Redis Version: {info.get('redis_version')}")
            logger.info(f"💾 Memory Used: {info.get('used_memory_human')}")
            return True

    except ConnectionError as e:
        logger.warning(f"⚠️  Redis connection failed: {e}")
        logger.info("💡 Application will continue without Redis features")
    except Exception as e:
        logger.error(f"❌ Unexpected Redis error: {e}")
        logger.info("💡 Application will continue without Redis features")

    return False
