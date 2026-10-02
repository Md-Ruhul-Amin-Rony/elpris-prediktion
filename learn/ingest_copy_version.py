"""
Bronze ingestion: fetch recent prices and weather, append them untouched.

Run:  uv run python learn/ingest_copy_version.py
"""
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

load_dotenv()

AREA = os.environ["PRICE_AREA"]
STATION = os.environ["STATION_ID"]
STOCKHOLM = ZoneInfo("Europe/Stockholm")
DAYS_BACK = 3
PARAMETERS = {"temperature": 1, "wind": 4}

PRICE_URL = "https://www.elprisetjustnu.se/api/v1/prices/{d:%Y}/{d:%m-%d}_{area}.json"
SMHI_URL = (
    "https://opendata-download-metobs.smhi.se/api/version/1.0"
    "/parameter/{param}/station/{station}/period/latest-months/data.json"
)


def fetch_prices(day):
    """Return the day's list of price intervals, or None if not published yet."""
    r = requests.get(PRICE_URL.format(d=day, area=AREA), timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def fetch_weather(param_id):
    """Return SMHI's list of readings for one parameter."""
    r = requests.get(SMHI_URL.format(param=param_id, station=STATION), timeout=30)
    r.raise_for_status()
    return r.json()["value"]


def main():
    today = datetime.now(STOCKHOLM).date()
    first_day = today - timedelta(days=DAYS_BACK)
    days = [first_day + timedelta(days=i) for i in range(DAYS_BACK + 2)]

    # Midnight Swedish time on the first day, as an aware instant.
    cutoff = datetime.combine(first_day, datetime.min.time(), tzinfo=STOCKHOLM)

    # --- fetch everything first ---------------------------------------
    price_rows = []
    for day in days:
        payload = fetch_prices(day)
        if payload is None:
            print(f"prices  {day}: not published, skipped")
            continue
        price_rows.append((AREA, day, Json(payload)))
        print(f"prices  {day}: {len(payload)} intervals")

    weather_rows = []
    for name, param_id in PARAMETERS.items():
        readings = fetch_weather(param_id)
        kept = 0
        for reading in readings:
            observed_at = datetime.fromtimestamp(reading["date"] / 1000, tz=UTC)
            if observed_at < cutoff:
                continue
            weather_rows.append((STATION, name, observed_at, Json(reading)))
            kept += 1
        print(f"weather {name}: kept {kept} of {len(readings)} readings")

    # --- then write everything in one transaction ---------------------
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    "INSERT INTO learn.raw__elpris (price_area, price_date, data) VALUES %s",
                    price_rows,
                )
                execute_values(
                    cur,
                    "INSERT INTO learn.raw__weather"
                    " (station, parameter, observed_at, data) VALUES %s",
                    weather_rows,
                )
    finally:
        conn.close()

    print(f"\ninserted {len(price_rows)} price days, {len(weather_rows)} weather readings")


if __name__ == "__main__":
    main()