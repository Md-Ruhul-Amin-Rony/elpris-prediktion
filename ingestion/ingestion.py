"""Ingestion service for landing raw electricity and weather data into PostgreSQL."""

import os
from datetime import UTC, datetime

import psycopg2
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from psycopg2.extras import Json

load_dotenv()

app = FastAPI()

SMHI_URL = (
    "https://opendata-download-metobs.smhi.se/api/version/1.0"
    "/parameter/{param}/station/{station}/period/latest-day/data.json"
)

PARAMETERS = {
    1: "temperature",
    4: "wind",
}


def fetch_weather_rows(station: str):
    """
    Fetch temperature and wind observations from SMHI for one station.

    SMHI exposes one weather parameter per request, so this function makes
    separate requests for temperature and wind and converts the observations
    into rows ready for insertion into raw__weather.

    Args:
        station: SMHI station identifier.

    Returns:
        A list of rows containing station, parameter, UTC observation time,
        and the original SMHI JSON payload.
    """
    rows = []

    for param_id, parameter_name in PARAMETERS.items():
        response = requests.get(
            SMHI_URL.format(
                param=param_id,
                station=station,
            ),
            timeout=15,
        )

        response.raise_for_status()

        for entry in response.json().get("value") or []:
            # SMHI timestamps are epoch milliseconds in UTC.
            observed_at = datetime.fromtimestamp(
                entry["date"] / 1000,
                tz=UTC,
            )

            rows.append(
                (
                    station,
                    parameter_name,
                    observed_at,
                    Json(entry),
                )
            )

    return rows


def insert_weather_rows(rows):
    """
    Insert raw weather observations into the bronze weather table.

    The source payload is stored unchanged in the data JSONB column.

    Args:
        rows: Weather rows prepared by fetch_weather_rows().

    Returns:
        Number of inserted rows.
    """
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO raw__weather
                (station, parameter, observed_at, data)
                VALUES (%s, %s, %s, %s)
                """,
                rows,
            )

        conn.commit()
        return len(rows)

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


@app.get("/ingestion/weather")
def ingest_weather(station: str):
    """
    Fetch recent SMHI weather observations and store them in raw__weather.

    The endpoint retrieves both temperature and wind for the requested
    station and inserts the observations into PostgreSQL.
    """
    try:
        rows = fetch_weather_rows(station)
        rows_inserted = insert_weather_rows(rows)

    except Exception as exc:
        raise HTTPException(
            500,
            f"Weather ingestion failed: {exc}",
        ) from exc

    return {
        "status": "ok",
        "station": station,
        "rows_inserted": rows_inserted,
    }


@app.get("/")
def read_root():
    """Return example requests for the available ingestion endpoints."""
    return {
        "electricity": "/ingestion/electricity?area=SE3&date=2026-08-25",
        "weather": "/ingestion/weather?station=97400",
    }


@app.get("/ingestion/electricity")
def ingest_electricity(area: str, date: str):
    """
    Fetch one day of electricity prices and store the raw API response.

    The endpoint calls elprisetjustnu.se for the requested price area and date.
    The complete JSON response is inserted as one append-only row in
    raw__elpris.

    Args:
        area: Swedish electricity price area, for example SE3.
        date: Date in YYYY-MM-DD format.

    Returns:
        A status response containing the area, date, and inserted row count.
    """
    try:
        year, month, day = date.split("-")

    except ValueError as exc:
        raise HTTPException(
            400,
            "Date must use format YYYY-MM-DD",
        ) from exc

    api_url = (
        "https://www.elprisetjustnu.se/api/v1/prices/"
        f"{year}/{month}-{day}_{area}.json"
    )

    response = requests.get(api_url, timeout=15)

    if not response.ok:
        raise HTTPException(
            502,
            f"Electricity API returned {response.status_code}",
        )

    payload = response.json()

    # DATABASE_URL contains the full cloud PostgreSQL connection string.
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    try:
        with conn.cursor() as cur:
            # Bronze/raw keeps the complete source payload unchanged.
            cur.execute(
                """
                INSERT INTO raw__elpris (price_area, price_date, data)
                VALUES (%s, %s, %s)
                """,
                (area, date, Json(payload)),
            )

        conn.commit()

    except Exception as exc:
        conn.rollback()
        raise HTTPException(
            500,
            f"Insert into database failed: {exc}",
        ) from exc

    finally:
        conn.close()

    return {
        "status": "ok",
        "area": area,
        "date": date,
        "rows_inserted": 1,
    }