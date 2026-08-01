from datetime import date, datetime
from zoneinfo import ZoneInfo


def is_future_date(given_date: date, tz: str) -> bool:
    local_tz = ZoneInfo(tz)
    today_local = datetime.now(local_tz).date()
    return given_date > today_local


def is_past_date(target_date: date):
    today = date.today()
    return target_date < today


def is_current_date(target_date: date):
    today = date.today()
    return target_date == today
