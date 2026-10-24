"""
Read Silver, build features, write Gold.

Idempotent: re-running updates rows instead of duplicating them.

Run:  uv run python learn/build_gold_copy_version.py
"""
import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from features_copy_version import build_features, daily_prices, daily_weather, fill_forecast_gaps
from psycopg2.extras import execute_values

load_dotenv()

# os.getenv, not os.environ[...]: this module gets imported by api/main.py
# for refresh_gold() -- a hard KeyError here would break that import in any
# environment without these set. main() checks them itself before using them.
AREA = os.getenv("PRICE_AREA")
STATION = os.getenv("STATION_ID")
TARGET = os.getenv("TARGET", "mean")

COLUMNS = [
    "price_area", "target_date",
    "tomorrow_temp_mean", "tomorrow_temp_min", "tomorrow_temp_max",
    "tomorrow_wind_mean", "price_today", "price_yesterday",
    "price_7d_ago", "price_7d_mean", "peak_today",
    "dayofweek", "month", "is_weekend",
    "n_intervals", "n_obs_temp", "n_obs_wind", "share_quality_g",
    "y",
]


def fetch_df(conn, sql, params):
    """Run a query and return the result as a DataFrame."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def to_plain(value):
    """Convert numpy scalars to plain Python types psycopg2 understands."""
    return value.item() if hasattr(value, "item") else value


def refresh_gold(conn, area: str, station: str, target: str) -> dict:
    """Rebuild learn.feat__daily for one area/station from current Silver.

    Idempotent -- re-running updates rows instead of duplicating them. The
    one place this logic lives -- called by main() for the scheduled daily
    run, and by api/main.py's POST /api/predict to rebuild Gold from
    whatever forecast was just re-fetched, instead of predicting from a
    row that is up to a day stale.
    """
    prices = fetch_df(
        conn,
        "SELECT starts_at, sek_per_kwh FROM learn.silver__elpris"
        " WHERE price_area = %(area)s ORDER BY starts_at",
        {"area": area},
    )
    weather = fetch_df(
        conn,
        "SELECT parameter, observed_at, value, quality"
        " FROM learn.silver__weather WHERE station = %(station)s"
        " ORDER BY observed_at",
        {"station": station},
    )
    forecast = fetch_df(
        conn,
        "SELECT parameter, valid_at, value"
        " FROM learn.silver__forecast WHERE station = %(station)s"
        " ORDER BY valid_at",
        {"station": station},
    )

    feat = build_features(daily_prices(prices), daily_weather(weather), target)

    feat, n_filled = fill_forecast_gaps(feat, forecast)

    feat = feat.reset_index()
    feat["target_date"] = feat["target_date"].dt.date      # Timestamp -> date
    feat.insert(0, "price_area", area)
    feat = feat.astype(object).where(pd.notna(feat), None)  # NaN -> None

    rows = [
        tuple(to_plain(v) for v in r)
        for r in feat[COLUMNS].itertuples(index=False)
    ]

    updatable = [c for c in COLUMNS if c not in ("price_area", "target_date")]
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updatable)

    with conn, conn.cursor() as cur:
        execute_values(
            cur,
            f"INSERT INTO learn.feat__daily ({', '.join(COLUMNS)}) VALUES %s"
            f" ON CONFLICT (price_area, target_date) DO UPDATE SET"
            f" {set_clause}, built_at = now()",
            rows,
            page_size=500,
        )

    return {
        "n_prices": len(prices),
        "n_weather": len(weather),
        "n_forecast": len(forecast),
        "n_filled": n_filled,
        "rows_written": len(rows),
    }


def main():
    if not AREA or not STATION:
        raise SystemExit("PRICE_AREA and STATION_ID must both be set.")

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        result = refresh_gold(conn, AREA, STATION, TARGET)
    finally:
        conn.close()

    print(
        f"silver: {result['n_prices']:,} price intervals, "
        f"{result['n_weather']:,} weather readings, "
        f"{result['n_forecast']:,} forecast readings"
    )
    print(f"forecast: filled {result['n_filled']} value(s) not yet observed")
    print(f"wrote {result['rows_written']} rows to learn.feat__daily")


if __name__ == "__main__":
    main()