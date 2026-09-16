"""Validation of the raw layer: count what arrived for the last N days.

Raw is never touched. Each run prints the outcome per check; nothing is
stored and nothing is rejected. Known gaps live in docs/validation.md.
"""

import argparse
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg2
from dotenv import load_dotenv

LOCAL_TZ = ZoneInfo("Europe/Stockholm")


def hours_in_local_day(day: date) -> int:
    """Hours in one local day: 24, or 23/25 on the DST change days."""
    start = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=LOCAL_TZ)
    return round((end.timestamp() - start.timestamp()) / 3600)


# Sweden moved from hourly to 15-minute day-ahead prices on this date
# (db/views.sql). A day has 24 rows before it and 96 after, DST days aside.
QUARTER_HOUR_FROM = date(2025, 10, 1)


def expected_price_intervals(day: date) -> int:
    """Price intervals one local day should contain."""
    per_hour = 4 if day >= QUARTER_HOUR_FROM else 1
    return hours_in_local_day(day) * per_hour


@dataclass
class CheckResult:
    """Outcome of one check: totals, verdict, and only the differences."""

    expected: int
    found: int
    ok: bool
    details: dict[str, int]


def compare_counts(expected: dict[str, int], found: dict[str, int]) -> CheckResult:
    """Compare what a window should contain with what raw actually holds.

    A key absent from `found` counts as 0, so a missing day is never silent.
    Every key where the counts differ ends up in details, surplus included.
    """
    details = {}
    for key, want in expected.items():
        got = found.get(key, 0)
        if got != want:
            details[key] = got
    return CheckResult(
        expected=sum(expected.values()),
        found=sum(found.get(key, 0) for key in expected),
        ok=not details,
        details=details,
    )


def window_days(today: date, days: int) -> list[date]:
    """The `days` complete local days ending yesterday, oldest first.

    Same rule as daily_ingest.py, so the check covers exactly what the
    ingestion fetched.
    """
    end_day = today - timedelta(days=1)
    return [end_day - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def expected_prices(days: list[date]) -> dict[str, int]:
    """Price intervals each day should contain, keyed by ISO date."""
    return {day.isoformat(): expected_price_intervals(day) for day in days}


def expected_weather(days: list[date], parameters: tuple[str, ...]) -> dict[str, int]:
    """Weather hours each day and parameter should contain, keyed 'date/parameter'."""
    return {
        f"{day.isoformat()}/{parameter}": hours_in_local_day(day)
        for day in days
        for parameter in parameters
    }


# Same constants as daily_ingest.py: the check covers what the ingestion writes.
STATION = "97400"
PARAMETERS = ("temperature", "wind")


def found_prices(conn, area: str, days: list[date]) -> dict[str, int]:
    """Price intervals per day in raw__elpris, newest ingestion per day."""
    sql = """
        SELECT price_date::text, jsonb_array_length(data)
        FROM (
            SELECT DISTINCT ON (price_date) price_date, data
            FROM raw__elpris
            WHERE price_area = %s AND price_date BETWEEN %s AND %s
            ORDER BY price_date, ingestion_timestamp DESC
        ) AS latest
    """
    with conn.cursor() as cur:
        cur.execute(sql, (area, days[0], days[-1]))
        return dict(cur.fetchall())


def found_weather(conn, station: str, days: list[date]) -> dict[str, int]:
    """Hours with a value per local day and parameter, newest ingestion per hour."""
    start = datetime.combine(days[0], time.min, tzinfo=LOCAL_TZ)
    end = datetime.combine(days[-1] + timedelta(days=1), time.min, tzinfo=LOCAL_TZ)
    sql = """
        SELECT (observed_at AT TIME ZONE 'Europe/Stockholm')::date::text || '/' || parameter,
               count(*)
        FROM (
            SELECT DISTINCT ON (parameter, observed_at) parameter, observed_at, data
            FROM raw__weather
            WHERE station = %s AND observed_at >= %s AND observed_at < %s
            ORDER BY parameter, observed_at, ingestion_timestamp DESC
        ) AS latest
        WHERE data ->> 'value' IS NOT NULL
        GROUP BY 1
    """
    with conn.cursor() as cur:
        cur.execute(sql, (station, start, end))
        return dict(cur.fetchall())


def main() -> int:
    """Count what arrived in raw for the last N complete days and print it."""
    parser = argparse.ArgumentParser(description="Validate raw__ for the last N complete days.")
    parser.add_argument("--days", type=int, default=7, help="Complete days to check. Default: 7.")
    args = parser.parse_args()
    if args.days < 1:
        raise SystemExit("--days must be at least 1")

    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set. Put it in .env or the environment.")
    area = os.environ.get("PRICE_AREA", "SE3")

    days = window_days(datetime.now(LOCAL_TZ).date(), args.days)

    conn = psycopg2.connect(url)
    try:
        prices = compare_counts(expected_prices(days), found_prices(conn, area, days))
        weather = compare_counts(
            expected_weather(days, PARAMETERS), found_weather(conn, STATION, days)
        )
    finally:
        conn.close()

    for name, result in (("elpris_intervals", prices), ("weather_hours", weather)):
        status = "ok" if result.ok else "MISSING"
        print(f"{name}: {result.found}/{result.expected} {status} ({days[0]} to {days[-1]})")
        for key, got in result.details.items():
            print(f"  {key}: found {got}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
