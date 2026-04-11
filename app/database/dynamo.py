from datetime import datetime
from typing import Optional

import aioboto3
from boto3.dynamodb.conditions import Key

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

    async def get_latest_telemetry(self, gateway_id: str) -> Optional[dict]:
        if not self._client:
            logger.warning("DynamoDB client not initialized")
            return None

        try:
            table = await self._get_table()
            response = await table.query(
                KeyConditionExpression=Key("gateway_id").eq(str(gateway_id)),
                ScanIndexForward=False,
                Limit=1,
            )

            items = response.get("Items", [])
            return items[0] if items else None

        except Exception as e:
            logger.error(f"❌ Error fetching latest telemetry for site with gateway id of {gateway_id}: {e}")
            return None

    async def get_telemetry_by_range(
        self,
        gateway_id: int,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[dict]:
        if not self._client:
            logger.warning("DynamoDB client not initialized")
            return []

        try:
            start_ms = int(start_ts.timestamp() * 1000)
            end_ms = int(end_ts.timestamp() * 1000)
            table = await self._get_table()

            response = await table.query(
                KeyConditionExpression=(
                    Key("gateway_id").eq(str(gateway_id)) & Key("ts_epoch_ms").between(start_ms, end_ms)
                ),
                ScanIndexForward=True,
            )

            items = response.get("Items", [])

            while "LastEvaluatedKey" in response:
                response = await table.query(
                    KeyConditionExpression=(
                        Key("gateway_id").eq(str(gateway_id)) & Key("ts_epoch_ms").between(start_ms, end_ms)
                    ),
                    ScanIndexForward=True,
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                items.extend(response.get("Items", []))

            return items

        except Exception as e:
            logger.error(f"❌ Error fetching telemetry range for site with gateway id {gateway_id}: {e}")
            return []

    async def get_readings_for_billing_period(
        self,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict:
        readings = await self.get_telemetry_by_range(
            gateway_id=gateway_id,
            start_ts=period_start,
            end_ts=period_end,
        )
        period_start_ms = int(period_start.timestamp() * 1000)
        period_end_ms = int(period_end.timestamp() * 1000)

        if not readings:
            return {
                "total_readings": 0,
                "actual_generation_kwh": 0.0,
                "period_start_ms": period_start_ms,
                "period_end_ms": period_end_ms,
            }

        kwh_values = [
            float(meter["kwh_total"])
            for reading in readings
            for meter in reading.get("meters", [])
            if "kwh_total" in meter
        ]

        actual_generation_kwh = 0.0
        if kwh_values:
            actual_generation_kwh = round(max(kwh_values) - min(kwh_values), 3)

        return {
            "total_readings": len(readings),
            "actual_generation_kwh": actual_generation_kwh,
            "period_start_ms": period_start_ms,
            "period_end_ms": period_end_ms,
        }

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
