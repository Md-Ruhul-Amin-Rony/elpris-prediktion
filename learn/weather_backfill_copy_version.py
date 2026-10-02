"""
Backfill historical weather into Bronze from two SMHI feeds:

  corrected-archive   quality-controlled history, CSV, ends ~3 months ago
  latest-months       recent ~4 months, JSON, same feed as the daily ingest

Run once:  uv run python learn/weather_backfill_copy_version.py 2024-08-01
"""
import os
import sys
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import psycopg2
import requests
from dotenv import load_dotenv
from ingest_copy_version import PARAMETERS, STATION, fetch_weather
from psycopg2.extras import Json, execute_values

load_dotenv()

STOCKHOLM = ZoneInfo("Europe/Stockholm")
ARCHIVE_URL = (
    "https://opendata-download-metobs.smhi.se/api/version/1.0"
    "/parameter/{param}/station/{station}/period/corrected-archive/data.csv"
)
INSERT_SQL = (
    "INSERT INTO learn.raw__weather"
    " (station, parameter, observed_at, data, source) VALUES %s"
)


def fetch_archive(param_id):
    """Yield (observed_at, fragment) for every data row in the archive CSV."""
    r = requests.get(ARCHIVE_URL.format(param=param_id, station=STATION), timeout=120)
    r.raise_for_status()
    lines = r.content.decode("utf-8-sig").splitlines()

    # Data starts on the line after the header that begins with "Datum;".
    start = next(i for i, line in enumerate(lines) if line.startswith("Datum;")) + 1

    for line in lines[start:]:
        if not line.strip():
            continue
        day, clock, value, quality = line.split(";")[:4]
        # The column header says "Tid (UTC)", so we label it UTC.
        observed_at = datetime.fromisoformat(f"{day}T{clock}").replace(tzinfo=UTC)
        yield observed_at, {"raw_line": line, "value": value, "quality": quality}


def main():
    start_day = date.fromisoformat(sys.argv[1])
    cutoff = datetime.combine(start_day, datetime.min.time(), tzinfo=STOCKHOLM)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn:
            with conn.cursor() as cur:
                for name, param_id in PARAMETERS.items():

                    # --- corrected archive: load once -----------------------
                    cur.execute(
                        "SELECT count(*) FROM learn.raw__weather"
                        " WHERE station = %s AND parameter = %s"
                        " AND source = 'corrected-archive'",
                        (STATION, name),
                    )
                    if cur.fetchone()[0] > 0:
                        print(f"{name:12} archive already loaded, skipped")
                    else:
                        rows = [
                            (STATION, name, observed_at, Json(fragment), "corrected-archive")
                            for observed_at, fragment in fetch_archive(param_id)
                            if observed_at >= cutoff
                        ]
                        execute_values(cur, INSERT_SQL, rows, page_size=1000)
                        print(f"{name:12} archive        {len(rows):>6,} readings")

                    # --- latest-months: covers the last few months ----------
                    rows = []
                    for reading in fetch_weather(param_id):
                        observed_at = datetime.fromtimestamp(
                            reading["date"] / 1000, tz=UTC
                        )
                        rows.append((STATION, name, observed_at, Json(reading), "latest-months"))
                    execute_values(cur, INSERT_SQL, rows, page_size=1000)
                    print(f"{name:12} latest-months  {len(rows):>6,} readings")
    finally:
        conn.close()


if __name__ == "__main__":
    main()