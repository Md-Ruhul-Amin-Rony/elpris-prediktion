"""
Forecast ingestion: fetch SMHI's point forecast, append it untouched.

SMHI's forecast API is keyed by longitude/latitude, not station id, so
each station needs its coordinates looked up once (see STATION_COORDS
below -- taken from SMHI's own station metadata, e.g.
https://opendata-download-metobs.smhi.se/api/version/1.0/parameter/1/station/97400.json).

Every fetch is appended as new rows (see learn/db/04_forecast_copy_version.sql
for why): nothing here overwrites an earlier forecast for the same hour.

Run:  uv run python learn/forecast_ingest_copy_version.py
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

load_dotenv()

STATION = os.environ["STATION_ID"]
STOCKHOLM = ZoneInfo("Europe/Stockholm")

# SMHI gives forecasts by point (lon, lat), not station id.
# Verified against SMHI's own station metadata for 97400 (Stockholm-Arlanda).
# Add an entry here before pointing STATION_ID at a different station.
STATION_COORDS = {
    "97400": (17.9545, 59.6269),  # lon, lat
}

FORECAST_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1"
    "/geotype/point/lon/{lon}/lat/{lat}/data.json"
)

# SMHI's flat field names -> this project's parameter names (matches raw__weather).
PARAMETERS = {
    "air_temperature": "temperature",
    "wind_speed": "wind",
}

# Only the near-term window is hourly; this project only ever needs tomorrow.
HOURS_AHEAD = 48


def fetch_forecast(lon, lat):
    """Return SMHI's point-forecast response."""
    r = requests.get(FORECAST_URL.format(lon=lon, lat=lat), timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    if STATION not in STATION_COORDS:
        raise SystemExit(
            f"No coordinates for station {STATION}. Add it to STATION_COORDS."
        )
    lon, lat = STATION_COORDS[STATION]

    payload = fetch_forecast(lon, lat)
    issued_at = datetime.fromisoformat(payload["referenceTime"].replace("Z", "+00:00"))

    cutoff = datetime.now(STOCKHOLM).astimezone(issued_at.tzinfo) + timedelta(hours=HOURS_AHEAD)

    rows = []
    for entry in payload["timeSeries"]:
        valid_at = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
        if valid_at > cutoff:
            continue
        for smhi_name, parameter in PARAMETERS.items():
            value = entry["data"].get(smhi_name)
            if value is None:
                continue
            rows.append((STATION, parameter, issued_at, valid_at, Json(entry)))

    if not rows:
        raise SystemExit("No forecast rows parsed -- check PARAMETERS against the API response.")

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    "INSERT INTO learn.stg__forecast"
                    " (station, parameter, issued_at, valid_at, data) VALUES %s",
                    rows,
                )
    finally:
        conn.close()

    print(f"forecast issued at {issued_at.isoformat()}")
    print(f"inserted {len(rows)} rows, covering up to {cutoff.isoformat()}")


if __name__ == "__main__":
    main()
