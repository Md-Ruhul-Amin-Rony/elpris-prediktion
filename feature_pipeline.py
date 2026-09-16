"""

Builds the complete historical feature table from Silver views according to teacher's suggestions
and can be run repeatedly without creating duplicate rows.
"""

from __future__ import annotations

import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

from model.train import (
    AREA_STATIONS,
    STOCKHOLM,
    build_features,
    daily_price_table,
    daily_weather_table,
)

load_dotenv()

PRICE_AREA = os.getenv("PRICE_AREA", "SE3").upper()

PARAM_TEMP = "temperature"
PARAM_WIND = "wind"


def load_prices_db(
    conn,
    area: str,
) -> pd.DataFrame:
    """Load Silver electricity prices into the shape train.py expects."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                starts_at,
                sek_per_kwh
            FROM silver__elpris
            WHERE price_area = %s
            ORDER BY starts_at
            """,
            (area,),
        )
        rows = cur.fetchall()

    if not rows:
        raise ValueError(
            f"No price rows found in silver__elpris for {area}."
        )

    prices = pd.DataFrame(
        rows,
        columns=["starts_at", "sek_per_kwh"],
    )

    prices["ts_utc"] = pd.to_datetime(
        prices["starts_at"],
        utc=True,
    )

    prices["ts_local"] = prices["ts_utc"].dt.tz_convert(
        STOCKHOLM
    )

    prices["date_local"] = prices["ts_local"].dt.date

    prices["sek_per_kwh"] = pd.to_numeric(
        prices["sek_per_kwh"],
        errors="coerce",
    )

    prices = prices.dropna(
        subset=["sek_per_kwh"]
    )

    return prices.sort_values(
        "ts_utc"
    ).reset_index(drop=True)


def load_weather_db(
    conn,
    station: int,
) -> pd.DataFrame:
    """Load and pivot Silver weather data for train.py."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                parameter,
                observed_at,
                value
            FROM silver__weather
            WHERE station = %s
              AND parameter IN (%s, %s)
            ORDER BY observed_at
            """,
            (
                str(station),
                PARAM_TEMP,
                PARAM_WIND,
            ),
        )
        rows = cur.fetchall()

    if not rows:
        raise ValueError(
            f"No weather rows found for station {station}."
        )

    long_weather = pd.DataFrame(
        rows,
        columns=[
            "parameter",
            "observed_at",
            "value",
        ],
    )

    wide_weather = long_weather.pivot(
        index="observed_at",
        columns="parameter",
        values="value",
    )

    wide_weather = wide_weather.rename(
        columns={
            PARAM_TEMP: "temp_c",
            PARAM_WIND: "wind_ms",
        }
    )

    missing_columns = {
        "temp_c",
        "wind_ms",
    } - set(wide_weather.columns)

    if missing_columns:
        raise ValueError(
            "Weather data is missing: "
            f"{sorted(missing_columns)}"
        )

    weather = wide_weather.reset_index()

    # daily_weather_table() implementation.
    weather["value"] = weather["temp_c"]

    weather["ts_utc"] = pd.to_datetime(
        weather["observed_at"],
        utc=True,
    )

    weather["ts_local"] = weather["ts_utc"].dt.tz_convert(
        STOCKHOLM
    )

    weather["date_local"] = weather["ts_local"].dt.date

    return weather.sort_values(
        "ts_utc"
    ).reset_index(drop=True)


def database_value(value):
    """Convert pandas and NumPy values into PostgreSQL-compatible values."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def database_boolean(value):
    """Convert the model's 0/1 weekend value into a database boolean."""
    value = database_value(value)
    return None if value is None else bool(value)


def write_features(
    conn,
    area: str,
    features: pd.DataFrame,
) -> tuple[int, int]:
    """Upsert feature rows and return inserted and updated counts."""
    if features.empty:
        return 0, 0

    sql = """
        INSERT INTO feat__daily (
            price_area,
            target_date,
            tomorrow_temp_mean,
            tomorrow_temp_min,
            tomorrow_temp_max,
            tomorrow_wind_mean,
            price_today,
            price_yesterday,
            price_7d_ago,
            price_7d_mean,
            peak_today,
            dayofweek,
            month,
            is_weekend,
            y
        )
        VALUES %s
        ON CONFLICT (price_area, target_date)
        DO UPDATE SET
            tomorrow_temp_mean = EXCLUDED.tomorrow_temp_mean,
            tomorrow_temp_min = EXCLUDED.tomorrow_temp_min,
            tomorrow_temp_max = EXCLUDED.tomorrow_temp_max,
            tomorrow_wind_mean = EXCLUDED.tomorrow_wind_mean,
            price_today = EXCLUDED.price_today,
            price_yesterday = EXCLUDED.price_yesterday,
            price_7d_ago = EXCLUDED.price_7d_ago,
            price_7d_mean = EXCLUDED.price_7d_mean,
            peak_today = EXCLUDED.peak_today,
            dayofweek = EXCLUDED.dayofweek,
            month = EXCLUDED.month,
            is_weekend = EXCLUDED.is_weekend,
            y = EXCLUDED.y,
            built_at = now()
        RETURNING (xmax = 0) AS was_inserted
    """

    rows = []

    for feature_date, row in features.iterrows():
        target_date = (
            pd.Timestamp(feature_date)
            + pd.Timedelta(days=1)
        ).date()

        rows.append(
            (
                area,
                target_date,
                database_value(row["tomorrow_temp_mean"]),
                database_value(row["tomorrow_temp_min"]),
                database_value(row["tomorrow_temp_max"]),
                database_value(row["tomorrow_wind_mean"]),
                database_value(row["price_today"]),
                database_value(row["price_yesterday"]),
                database_value(row["price_7d_ago"]),
                database_value(row["price_7d_mean"]),
                database_value(row["peak_today"]),
                database_value(row["dayofweek"]),
                database_value(row["month"]),
                database_boolean(row["is_weekend"]),
                database_value(row["y"]),
            )
        )

    with conn.cursor() as cur:
        results = execute_values(cur, sql, rows, fetch=True)

    inserted = sum(
        was_inserted
        for (was_inserted,) in results
    )

    updated = len(results) - inserted

    return inserted, updated


def refresh_daily_features(
    conn,
    area: str,
) -> tuple[int, int]:
    """Build daily features using the existing train.py functions."""
    station, _station_name = AREA_STATIONS[area]

    prices = load_prices_db(
        conn,
        area,
    )

    weather = load_weather_db(
        conn,
        station,
    )

    daily_prices = daily_price_table(
        prices
    )

    daily_weather = daily_weather_table(
        weather
    )

    features = build_features(
        daily_prices,
        daily_weather,
    )

    return write_features(
        conn,
        area,
        features,
    )


def main() -> None:
    database_url = os.environ["DATABASE_URL"]

    with psycopg2.connect(database_url) as conn:
        inserted, updated = refresh_daily_features(
            conn,
            PRICE_AREA,
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*),
                    MIN(target_date),
                    MAX(target_date)
                FROM feat__daily
                WHERE price_area = %s
                """,
                (PRICE_AREA,),
            )
            total, first_date, last_date = cur.fetchone()

    print(
        f"wrote {inserted + updated} rows for {PRICE_AREA}; "
        f"inserted={inserted}; updated={updated}; "
        f"table_total={total}; "
        f"date_range={first_date} to {last_date}"
    )


if __name__ == "__main__":
    main()