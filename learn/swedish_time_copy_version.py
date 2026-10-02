"""
Calendar facts about Swedish local days.

Pure functions: no database, no network, same input always gives the
same output. That makes them easy to reuse and easy to test.
"""
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")
QUARTER_HOUR_FROM = date(2025, 10, 1)


def local_midnight(day):
    """Midnight at the start of `day`, Swedish time, as an aware datetime."""
    return datetime.combine(day, time.min, tzinfo=STOCKHOLM)


def hours_in_local_day(day):
    """23, 24 or 25, depending on daylight saving."""
    start = local_midnight(day).astimezone(UTC)
    end = local_midnight(day + timedelta(days=1)).astimezone(UTC)
    return round((end - start).total_seconds() / 3600)


def expected_price_intervals(day):
    """How many price rows one Swedish day should have."""
    per_hour = 4 if day >= QUARTER_HOUR_FROM else 1
    return hours_in_local_day(day) * per_hour


def expected_weather_readings(day):
    """How many hourly weather readings one Swedish day should have."""
    return hours_in_local_day(day)