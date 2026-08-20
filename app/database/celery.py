from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

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
    connect_args={
        "options": "-ctimezone=UTC",
        "sslmode": "require",
    },
)
_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


@contextmanager
def get_celery_db_session():
    """Context manager that yields a synchronous SQLAlchemy session for Celery tasks.

    Commits on success and rolls back on any exception, always closing the session.

    Yields:
        A SQLAlchemy Session bound to the sync database engine.

    Raises:
        Exception: Re-raises any exception after rolling back the session.
    """
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
    """Singleton synchronous DynamoDB client used by Celery billing and stats tasks."""

    _instance: Optional["CeleryDynamoClient"] = None
    _table = None

    def __new__(cls):
        """Return the existing singleton instance or create one.

        Returns:
            The singleton CeleryDynamoClient instance.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init(self):
        """Connect to DynamoDB using boto3 and bind the configured time-series table.

        Returns:
            None

        Raises:
            Exception: If the boto3 resource or table reference cannot be established.
        """
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
        """Compute the millisecond epoch timestamps for the start and end of a given day.

        Args:
            date: A datetime object representing any moment within the target day.

        Returns:
            A tuple of (start_of_day_ms, end_of_day_ms) as integer millisecond timestamps.
        """
        start_of_day = date.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        end_of_day = date.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        )
        return int(start_of_day.timestamp() * 1000), int(end_of_day.timestamp() * 1000)

    def get_readings_for_billing_period(
        self,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
        is_multi_day: bool = False,
    ) -> tuple[dict, dict] | None:
        """Fetch the boundary DynamoDB readings for a gateway over a billing period.

        Queries for the earliest reading on period_start day and the latest on period_end day.

        Args:
            gateway_id: The gateway identifier used as the DynamoDB partition key.
            period_start: The start date of the billing period.
            period_end: The end date of the billing period.
            is_multi_day: A flag for multi day period.
        Returns:
            A tuple of (start_item, end_item) dicts from DynamoDB, or None if readings are missing.
        """
        if not self._table:
            logger.warning("DynamoDB table not initialized")
            return None

        try:
            start_day_ts, end_day_ts = self._get_day_epoch_range(period_start)

            if is_multi_day:
                _, end_day_ts = self._get_day_epoch_range(period_end)

            start_response = self._table.query(
                KeyConditionExpression=(Key("gateway_id").eq(gateway_id) & Key("ts_epoch_ms").gte(start_day_ts)),
                ScanIndexForward=True,
                Limit=1,
            )

            end_response = self._table.query(
                KeyConditionExpression=(Key("gateway_id").eq(gateway_id) & Key("ts_epoch_ms").lte(end_day_ts)),
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
            logger.error(f"Error fetching billing period readings for gateway {gateway_id}: {e}")
            return None

    def get_site_readings_by_date_and_interval(
        self, gateway_id: str, date_at: date, tz: str, interval_minutes: int = 30
    ) -> Optional[list[dict]]:
        """Fetch nearest-prior DynamoDB readings for a gateway at fixed intervals.

        Queries readings between 9:00am and 15:00pm for date_at, in interval_minutes
        steps. Boundaries stop at the current site-local time, so a still-in-progress
        day returns fewer than 13 items instead of guessing future readings.

        Args:
            gateway_id: The gateway identifier used as the DynamoDB partition key.
            date_at: Specific date.
            tz: Site timezone, used to resolve boundaries and "now".
            interval_minutes: Spacing between boundary points, in minutes.

        Returns:
            A list of reading dicts, one per elapsed boundary (max 13), or None if
            the table isn't initialized.
        """
        if not self._table:
            logger.warning("DynamoDB table not initialized")
            return None

        local_tz = ZoneInfo(tz)
        window_start = datetime.combine(date_at, time(9, 0), tzinfo=local_tz)
        window_end = datetime.combine(date_at, time(15, 0), tzinfo=local_tz)
        now_local = datetime.now(local_tz)

        effective_end = min(window_end, now_local)

        boundaries: list[datetime] = []
        current = window_start
        while current <= effective_end:
            boundaries.append(current)
            current += timedelta(minutes=interval_minutes)

        results = []
        seen_timestamps = set()
        try:
            for boundary in boundaries:
                boundary_ts = int(boundary.astimezone(timezone.utc).timestamp() * 1000)
                response = self._table.query(
                    KeyConditionExpression=Key("gateway_id").eq(gateway_id) & Key("ts_epoch_ms").lte(boundary_ts),
                    ScanIndexForward=False,
                    Limit=1,
                )
                items = response.get("Items", [])
                if len(items):
                    item = items[0]
                    ts = item.get("ts_epoch_ms")
                    if ts in seen_timestamps:
                        results.append(None)
                    else:
                        seen_timestamps.add(ts)
                        results.append(item)
                else:
                    results.append(None)

            return results
        except Exception as e:
            logger.error(f"❌ Failed to query DynamoDB for gateway {gateway_id}: {e}")
            raise


celery_dynamo_client = CeleryDynamoClient()
