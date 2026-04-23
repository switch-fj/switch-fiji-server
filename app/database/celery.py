from contextlib import contextmanager
from datetime import datetime
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Config
from app.core.logger import setup_logger

logger = setup_logger(__name__)

_engine = create_engine(
    url=Config.DATABASE_URL_SYNC,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
)
_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def get_celery_db_session():
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class CeleryDynamoClient:
    _instance: Optional["CeleryDynamoClient"] = None
    _table = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init(self):
        if self._table is None:
            try:
                dynamodb = boto3.resource(
                    "dynamodb",
                    aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
                    region_name=Config.AWS_REGION,
                )
                self._table = dynamodb.Table(Config.AWS_TIME_SERIES_TABLE)
                logger.info("✅ Celery DynamoDB connection established")
            except Exception as e:
                logger.error(f"❌ Failed to connect to DynamoDB: {e}")
                raise

    @staticmethod
    def _get_day_epoch_range(date: datetime) -> tuple[int, int]:
        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)
        return int(start_of_day.timestamp() * 1000), int(end_of_day.timestamp() * 1000)

    def get_readings_for_billing_period(
        self,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> tuple[dict, dict] | None:
        if not self._table:
            logger.warning("DynamoDB table not initialized")
            return None

        try:
            start_ms, _ = self._get_day_epoch_range(period_start)
            _, end_ms = self._get_day_epoch_range(period_end)

            start_response = self._table.query(
                KeyConditionExpression=(Key("gateway_id").eq(gateway_id) & Key("ts_epoch_ms").gte(start_ms)),
                ScanIndexForward=True,
                Limit=1,
            )

            end_response = self._table.query(
                KeyConditionExpression=(Key("gateway_id").eq(gateway_id) & Key("ts_epoch_ms").lte(end_ms)),
                ScanIndexForward=False,
                Limit=1,
            )

            start_items = start_response.get("Items", [])
            end_items = end_response.get("Items", [])

            if not start_items or not end_items:
                logger.warning(f"Missing boundary readings for gateway {gateway_id}")
                return None

            return start_items[0], end_items[0]

        except Exception as e:
            logger.error(f"❌ Error fetching billing period readings for gateway {gateway_id}: {e}")
            return None


celery_dynamo_client = CeleryDynamoClient()
