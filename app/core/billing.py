from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from dateutil.relativedelta import relativedelta

from app.core.config import Config
from app.core.logger import setup_logger
from app.modules.contracts.schema import ContractBillingFrequencyEnum

logger = setup_logger(__name__)


class Billing:
    @staticmethod
    def get_current_billing_period(
        commissioned_at: datetime,
        billing_frequency: str,
        as_of: datetime = None,
    ):
        if as_of is None:
            as_of = datetime.now(timezone.utc)

        try:
            freq = ContractBillingFrequencyEnum(billing_frequency.lower())
        except ValueError:
            raise ValueError(f"Unsupported billing frequency: {billing_frequency}")

        diff = relativedelta(as_of, commissioned_at)
        match freq:
            case ContractBillingFrequencyEnum.WEEKLY:
                total_days = (as_of - commissioned_at).days
                n = total_days // 7
                delta = relativedelta(weeks=1)
            case ContractBillingFrequencyEnum.BI_WEEKLY:
                total_days = (as_of - commissioned_at).days
                n = total_days // 14
                delta = relativedelta(weeks=2)
            case ContractBillingFrequencyEnum.MONTHLY:
                total_months = diff.years * 12 + diff.months
                n = total_months // 1
                delta = relativedelta(months=1)
            case ContractBillingFrequencyEnum.QUARTERLY:
                total_months = diff.years * 12 + diff.months
                n = total_months // 3
                delta = relativedelta(months=3)
            case ContractBillingFrequencyEnum.SEMI_ANNUALLY:
                total_months = diff.years * 12 + diff.months
                n = total_months // 6
                delta = relativedelta(months=6)
            case ContractBillingFrequencyEnum.ANNUALLY:
                n = diff.years
                delta = relativedelta(years=1)

        period_start = commissioned_at + (delta * n)
        period_end = period_start + delta - relativedelta(seconds=1)

        return period_start, period_end

    @staticmethod
    def get_readings_for_billing_period_sync(
        gateway_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict:
        start_ms = int(period_start.timestamp() * 1000)
        end_ms = int(period_end.timestamp() * 1000)

        try:
            dynamodb = boto3.resource(
                "dynamodb",
                region_name=Config.AWS_REGION,
                aws_access_key_id=Config.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=Config.AWS_SECRET_ACCESS_KEY,
            )
            table = dynamodb.Table(Config.AWS_TIME_SERIES_TABLE)

            query_kwargs = {
                "KeyConditionExpression": (
                    Key("gateway_id").eq(gateway_id) & Key("ts_epoch_ms").between(start_ms, end_ms)
                ),
                "ScanIndexForward": True,
            }

            items = []
            while True:
                response = table.query(**query_kwargs)
                items.extend(response.get("Items", []))
                if "LastEvaluatedKey" not in response:
                    break
                query_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]

            kwh_values = [
                float(meter["kwh_total"])
                for reading in items
                for meter in reading.get("meters", [])
                if "kwh_total" in meter
            ]

            actual_generation_kwh = 0.0
            if kwh_values:
                actual_generation_kwh = round(max(kwh_values) - min(kwh_values), 3)

            return {
                "actual_generation_kwh": actual_generation_kwh,
                "total_readings": len(items),
                "period_start_ms": start_ms,
                "period_end_ms": end_ms,
            }

        except Exception as e:
            logger.error(f"❌ Error fetching billing period readings for gateway {gateway_id}: {e}")
            return {
                "actual_generation_kwh": 0.0,
                "total_readings": 0,
                "period_start_ms": start_ms,
                "period_end_ms": end_ms,
            }
