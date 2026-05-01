from datetime import datetime
from typing import Optional

from app.core.config import Config
from app.core.logger import setup_logger
from app.database.timestream import timestream_connection

logger = setup_logger(__name__)

DB = Config.AWS_TIMESTREAM_DATABASE
TBL = Config.AWS_TIMESTREAM_TABLE


class TimestreamService:
    def _billing_query(
        self,
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> str:
        start_ms = int(period_start.timestamp() * 1000)
        end_ms = int(period_end.timestamp() * 1000)
        return f"""
            SELECT
                slave_id,
                MAX(CAST(measure_value AS DOUBLE)) -
                MIN(CAST(measure_value AS DOUBLE)) AS kwh_consumed
            FROM "{DB}"."{TBL}"
            WHERE gateway_id   = '{gateway_id}'
            AND device_type  = 'meter'
            AND measure_name = 'kwh_total'
            AND time BETWEEN from_milliseconds({start_ms})
                        AND from_milliseconds({end_ms})
            GROUP BY slave_id
        """

    def _compute_billing(
        self,
        rows: list[dict],
        period_start: datetime,
        period_end: datetime,
    ) -> dict:
        total_kwh = sum(float(r["kwh_consumed"]) for r in rows if r.get("kwh_consumed") is not None)
        return {
            "actual_generation_kwh": round(total_kwh, 3),
            "total_readings": len(rows),
            "period_start_ms": int(period_start.timestamp() * 1000),
            "period_end_ms": int(period_end.timestamp() * 1000),
        }

    def _parse_rows(self, columns: list, rows: list) -> list[dict]:
        """Map Timestream column/row format into list of dicts."""
        col_names = [col["Name"] for col in columns]
        result = []
        for row in rows:
            record = {}
            for col_name, datum in zip(col_names, row["Data"]):
                record[col_name] = None if datum.get("NullValue") else datum.get("ScalarValue")
            result.append(record)
        return result

    async def _run_query_async(self, query: str) -> list[dict]:
        """Run a Timestream query asynchronously — FastAPI."""
        try:
            items = []
            async with await timestream_connection.get_async_client() as client:
                paginator = await client.get_paginator("query")
                async for page in paginator.paginate(QueryString=query):
                    items.extend(self._parse_rows(page["ColumnInfo"], page["Rows"]))
            return items
        except Exception as e:
            logger.error(f"❌ Timestream async query failed: {e}\nQuery: {query}")
            return []

    def _run_query_sync(self, query: str) -> list[dict]:
        """Run a Timestream query synchronously — Celery."""
        try:
            client = timestream_connection.get_sync_client()
            paginator = client.get_paginator("query")
            items = []
            for page in paginator.paginate(QueryString=query):
                items.extend(self._parse_rows(page["ColumnInfo"], page["Rows"]))
            return items
        except Exception as e:
            logger.error(f"❌ Timestream sync query failed: {e}\nQuery: {query}")
            return []

    @staticmethod
    async def get_latest_telemetry(gateway_id: str) -> Optional[dict]:
        """Latest reading for a gateway — engineer dashboard device status."""
        query = f"""
            SELECT *
            FROM "{DB}"."{TBL}"
            WHERE gateway_id = '{gateway_id}'
            ORDER BY time DESC
            LIMIT 1
        """
        results = await TimestreamService._run_query_async(query)
        return results[0] if results else None

    @staticmethod
    async def get_telemetry_by_range(
        gateway_id: str,
        start_ts: datetime,
        end_ts: datetime,
    ) -> list[dict]:
        """All readings for a gateway within a time range — charts."""
        start_ms = int(start_ts.timestamp() * 1000)
        end_ms = int(end_ts.timestamp() * 1000)

        query = f"""
            SELECT *
            FROM "{DB}"."{TBL}"
            WHERE gateway_id = '{gateway_id}'
            AND time BETWEEN from_milliseconds({start_ms})
                        AND from_milliseconds({end_ms})
            ORDER BY time ASC
        """
        return await TimestreamService._run_query_async(query)

    @staticmethod
    async def get_readings_for_billing_period(
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict:
        """Actual generation for billing period — async version."""
        return TimestreamService._compute_billing(
            rows=await TimestreamService._run_query_async(
                TimestreamService._billing_query(gateway_id, period_start, period_end)
            ),
            period_start=period_start,
            period_end=period_end,
        )

    @staticmethod
    def get_readings_for_billing_period_sync(
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict:
        """Actual generation for billing period — sync version for Celery."""
        return TimestreamService._compute_billing(
            rows=TimestreamService._run_query_sync(
                TimestreamService._billing_query(gateway_id, period_start, period_end)
            ),
            period_start=period_start,
            period_end=period_end,
        )
