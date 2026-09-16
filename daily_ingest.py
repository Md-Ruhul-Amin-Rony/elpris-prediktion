"""Daily ingestion script for electricity and weather data."""

import argparse
import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import Json

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
PRICE_AREA = os.getenv("PRICE_AREA", "SE3")
STATION = os.getenv("STATION_ID", "97400")

SMHI_URL = (
    "https://opendata-download-metobs.smhi.se/api/version/1.0"
    "/parameter/{param}/station/{station}/period/latest-months/data.json"
)

ELPRIS_URL = (
    "https://www.elprisetjustnu.se/api/v1/prices/"
    "{year}/{month_day}_{area}.json"
)

PARAMETERS = {
    1: "temperature",
    4: "wind",
}


def ingest_prices(conn, area: str, day: date) -> int:
    """
    Fetch one day of electricity prices and insert the raw payload.

    Returns:
        Number of rows written to raw__elpris.
    """
    year = day.strftime("%Y")
    month_day = day.strftime("%m-%d")

    api_url = ELPRIS_URL.format(
        year=year,
        month_day=month_day,
        area=area,
    )

    response = requests.get(api_url, timeout=15)
    response.raise_for_status()

    payload = response.json()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO raw__elpris (price_area, price_date, data)
            VALUES (%s, %s, %s)
            """,
            (area, day, Json(payload)),
        )

    return 1


def ingest_weather(conn, station: str, start_day: date, end_day: date) -> int:
    """
    Fetch weather observations and insert the requested date range.

    SMHI latest-months is used so missed ingestion days can be recovered.
    The original source payload is stored unchanged.

    Returns:
        Number of rows written to raw__weather.
    """
    rows = []

    for param_id, parameter_name in PARAMETERS.items():
        response = requests.get(
            SMHI_URL.format(
                param=param_id,
                station=station,
            ),
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json().get("value") or []

        for entry in payload:
            # observed_at is required by the bronze table.
            # SMHI supplies date as epoch milliseconds in UTC.
            if entry.get("date") is None:
                continue

            observed_at = datetime.fromtimestamp(entry["date"] / 1000, tz=UTC)

            # Compare using the Swedish calendar day so weather and
            # electricity use the same local-date boundary.
            stockholm_time = observed_at.astimezone(ZoneInfo("Europe/Stockholm"))
            observed_day = stockholm_time.date()

            if start_day <= observed_day <= end_day:
                rows.append(
                    (station, parameter_name, observed_at, Json(entry))
                )

    if not rows:
        return 0

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO raw__weather
            (station, parameter, observed_at, data)
            VALUES (%s, %s, %s, %s)
            """,
            rows,
        )

    return len(rows)


def main():
    """Run the daily electricity and weather ingestion."""
    parser = argparse.ArgumentParser(description="Ingest recent electricity and weather data.")
    
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of recent complete days to ingest. Default: 7.",
    )
    args = parser.parse_args()

    if args.days < 1:
        raise SystemExit("--days must be at least 1")

    # Work with complete Swedish calendar days.
    today = datetime.now(ZoneInfo("Europe/Stockholm")).date()
    end_day = today - timedelta(days=1)
    start_day = end_day - timedelta(days=args.days - 1)

    price_rows = 0
    weather_rows = 0

    conn = psycopg2.connect(DATABASE_URL)

    try:
        # Electricity API supports one date per request.
        for offset in range(args.days):
            day = start_day + timedelta(days=offset)
            price_rows += ingest_prices(
                conn,
                PRICE_AREA,
                day,
            )

        # Weather is fetched from latest-months and filtered
        # to the same rolling date window.
        weather_rows = ingest_weather(
            conn,
            STATION,
            start_day,
            end_day,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    total_rows = price_rows + weather_rows

    print(f"Date range: {start_day} to {end_day}")
    print(f"Electricity rows written: {price_rows}")
    print(f"Weather rows written: {weather_rows}")
    print(f"Total rows written: {total_rows}")

    if total_rows == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()