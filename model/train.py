"""
Training pipeline: predict tomorrow's electricity price.

This version reads prepared daily features from feat__daily
in PostgreSQL/Neon.

Feature engineering is handled separately by feature_pipeline.py,
which builds feat__daily from the Silver layer.

Run:

    uv run python model/train.py

Configuration comes from the environment:

    PRICE_AREA   SE1 | SE2 | SE3 | SE4
    TARGET       mean | peak
"""

from __future__ import annotations

import json
import os
import pickle
import zoneinfo
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(__file__).resolve().parent / "model.pkl"

PRICE_AREA = os.getenv("PRICE_AREA", "SE3").upper()
TARGET = os.getenv("TARGET", "mean").lower()

TRAIN_START_DATE = os.getenv("TRAIN_START_DATE")
TRAIN_END_DATE = os.getenv("TRAIN_END_DATE")

STOCKHOLM = zoneinfo.ZoneInfo("Europe/Stockholm")

# Which SMHI station supplies the weather for each price area.
AREA_STATIONS = {
    "SE1": (162860, "Lulea-Kallax Flygplats"),
    "SE2": (134100, "Ostersunds Flygplats"),
    "SE3": (97400, "Stockholm-Bromma Flygplats"),
    "SE4": (53430, "Malmo A"),
}


# --------------------------------------------------------------------------
# database loading
# --------------------------------------------------------------------------
def get_connection():
    """Create a connection to the PostgreSQL/Neon database."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise SystemExit(
            "DATABASE_URL is not set. Add your Neon connection string to .env."
        )

    return psycopg2.connect(database_url)


def load_features(
    area: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Load prepared model features from feat__daily."""

    query = """
        SELECT
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
        FROM feat__daily
        WHERE price_area = %s
          AND target_date BETWEEN %s AND %s
        ORDER BY target_date
    """

    with get_connection() as conn:
        df = pd.read_sql_query(
            query,
            conn,
            params=(area, start_date, end_date),
        )

    if df.empty:
        raise SystemExit(
            f"No feature rows found for {area} "
            f"between {start_date} and {end_date}."
        )

    df["target_date"] = pd.to_datetime(df["target_date"])
    df = df.set_index("target_date")

    return df


def load_prices(area: str) -> pd.DataFrame:
    """Load electricity prices from the Silver layer."""

    query = """
        SELECT
            price_area,
            price_date,
            starts_at,
            ends_at,
            sek_per_kwh
        FROM silver__elpris
        WHERE price_area = %s
        ORDER BY starts_at
    """

    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=(area,))

    if df.empty:
        raise SystemExit(f"No price rows found for {area}.")

    df["ts_utc"] = pd.to_datetime(
        df["starts_at"],
        utc=True,
    )

    df["ts_local"] = df["ts_utc"].dt.tz_convert(STOCKHOLM)
    df["date_local"] = df["ts_local"].dt.date

    df["sek_per_kwh"] = pd.to_numeric(
        df["sek_per_kwh"],
        errors="coerce",
    )

    df = df.dropna(subset=["sek_per_kwh"])

    return df.sort_values("ts_utc").reset_index(drop=True)


def load_weather(area: str) -> pd.DataFrame:
    """Load weather observations from the Silver layer."""

    station, station_name = AREA_STATIONS[area]

    query = """
        SELECT
            station,
            parameter,
            observed_at,
            value,
            quality
        FROM silver__weather
        WHERE station = %s::text
          AND parameter IN ('temperature', 'wind')
        ORDER BY observed_at
    """

    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=(station,))

    if df.empty:
        raise SystemExit(
            f"No weather rows found for station {station} ({station_name})."
        )

    df["ts_utc"] = pd.to_datetime(
        df["observed_at"],
        utc=True,
    )

    df["ts_local"] = df["ts_utc"].dt.tz_convert(STOCKHOLM)
    df["date_local"] = df["ts_local"].dt.date

    df["value"] = pd.to_numeric(
        df["value"],
        errors="coerce",
    )

    # Convert the Silver parameter rows into the same columns
    # that the original CSV pipeline used.
    df["temp_c"] = df["value"].where(
        df["parameter"] == "temperature"
    )

    df["wind_ms"] = df["value"].where(
        df["parameter"] == "wind"
    )

    return df.sort_values("ts_utc").reset_index(drop=True)


# --------------------------------------------------------------------------
# aggregate to one row per day
# --------------------------------------------------------------------------
def daily_price_table(prices: pd.DataFrame) -> pd.DataFrame:
    """Collapse the price series to one row per local calendar day."""

    grouped = prices.groupby("date_local")["sek_per_kwh"]

    daily = pd.DataFrame(
        {
            "mean_price": grouped.mean(),
            "peak_price": grouped.max(),
            "min_price": grouped.min(),
            "n_intervals": grouped.size(),
        }
    )

    daily.index = pd.to_datetime(daily.index)

    return daily.sort_index()


def daily_weather_table(weather: pd.DataFrame) -> pd.DataFrame:
    """Create one row per day from the Silver weather observations."""

    grouped = weather.groupby("date_local")

    daily = pd.DataFrame(
        {
            "temp_mean": grouped["temp_c"].mean(),
            "temp_min": grouped["temp_c"].min(),
            "temp_max": grouped["temp_c"].max(),
            "wind_mean": grouped["wind_ms"].mean(),
            "n_obs": grouped["value"].count(),
        }
    )

    daily.index = pd.to_datetime(daily.index)

    return daily.sort_index()


# --------------------------------------------------------------------------
# features
# --------------------------------------------------------------------------
def build_features(
    daily_price: pd.DataFrame,
    daily_weather: pd.DataFrame,
) -> pd.DataFrame:
    """Build one feature row per prediction day."""

    df = daily_price.join(
        daily_weather,
        how="left",
    )

    # Tomorrow's weather.
    for col in (
        "temp_mean",
        "temp_min",
        "temp_max",
        "wind_mean",
    ):
        df[f"tomorrow_{col}"] = df[col].shift(-1)

    # Price history available at prediction time.
    df["price_today"] = df["mean_price"]
    df["price_yesterday"] = df["mean_price"].shift(1)
    df["price_7d_ago"] = df["mean_price"].shift(7)
    df["price_7d_mean"] = df["mean_price"].rolling(
        7,
        min_periods=3,
    ).mean()
    df["peak_today"] = df["peak_price"]

    # Calendar features.
    df["dayofweek"] = df.index.dayofweek
    df["month"] = df.index.month
    df["is_weekend"] = (
        df.index.dayofweek >= 5
    ).astype(int)

    # Tomorrow's target.
    label_col = (
        "mean_price"
        if TARGET == "mean"
        else "peak_price"
    )

    df["y"] = df[label_col].shift(-1)

    return df


FEATURES = [
    "tomorrow_temp_mean",
    "tomorrow_temp_min",
    "tomorrow_temp_max",
    "tomorrow_wind_mean",
    "price_today",
    "price_yesterday",
    "price_7d_ago",
    "price_7d_mean",
    "peak_today",
    "dayofweek",
    "month",
    "is_weekend",
]


# --------------------------------------------------------------------------
# train
# --------------------------------------------------------------------------
def main() -> None:
    if TARGET not in ("mean", "peak"):
        raise SystemExit(
            f"TARGET must be 'mean' or 'peak', got {TARGET!r}"
        )

    if PRICE_AREA not in AREA_STATIONS:
        raise SystemExit(
            f"Unknown PRICE_AREA {PRICE_AREA!r}. "
            f"Use one of: {sorted(AREA_STATIONS)}"
        )

    print(
        f"area={PRICE_AREA}  target={TARGET}"
    )

    # Load prepared features directly from the feature table.
    if not TRAIN_START_DATE or not TRAIN_END_DATE:
        raise SystemExit(
            "TRAIN_START_DATE and TRAIN_END_DATE must be set in .env."
        )

    df = load_features(
        PRICE_AREA,
        TRAIN_START_DATE,
        TRAIN_END_DATE,
    )

    print(
        f"feature rows {len(df)} "
        f"({df.index.min().date()} .. "
        f"{df.index.max().date()})"
    )

    # Keep only rows that contain all required model features
    # and a valid target value.
    usable = df.dropna(
        subset=FEATURES + ["y"]
    )

    print(
        f"usable rows  {len(usable)} "
        f"of {len(df)}"
    )

    if len(usable) < 2:
        raise SystemExit(
            "Not enough usable rows to train the model."
        )

    # Chronological train/test split.
    cutoff = int(len(usable) * 0.8)

    train = usable.iloc[:cutoff]
    test = usable.iloc[cutoff:]

    print(
        f"train {len(train)} "
        f"({train.index.min().date()} .. "
        f"{train.index.max().date()})"
    )

    print(
        f"test  {len(test)} "
        f"({test.index.min().date()} .. "
        f"{test.index.max().date()})"
    )

    if train.empty or test.empty:
        raise SystemExit(
            "Train/test split produced an empty dataset."
        )

    # Same model as the original baseline.
    model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.06,
        max_depth=6,
        min_samples_leaf=15,
        l2_regularization=1.0,
        random_state=42,
    )

    model.fit(
        train[FEATURES],
        train["y"],
    )

    # Evaluate.
    pred = model.predict(
        test[FEATURES]
    )

    mae = mean_absolute_error(
        test["y"],
        pred,
    )

    r2 = r2_score(
        test["y"],
        pred,
    )

    # Naive baseline:
    # tomorrow = today.
    naive = (
        test["price_today"]
        if TARGET == "mean"
        else test["peak_today"]
    )

    naive_mae = mean_absolute_error(
        test["y"],
        naive,
    )

    print()
    print(
        f"  MAE          {mae:.4f} SEK/kWh"
    )

    print(
        f"  R2           {r2:.3f}"
    )

    print(
        f"  naive MAE    {naive_mae:.4f} SEK/kWh "
        "(tomorrow = today)"
    )

    verdict = (
        "beats"
        if mae < naive_mae
        else "LOSES TO"
    )

    print(
        f"  model {verdict} the naive baseline"
    )

    # Save model.
    payload = {
        "model": model,
        "features": FEATURES,
        "price_area": PRICE_AREA,
        "target": TARGET,
        "train_start_date": TRAIN_START_DATE,
        "train_end_date": TRAIN_END_DATE,
        "n_feature_rows": len(df),
        "n_usable_rows": len(usable),
        "trained_at": datetime.now(
            tz=STOCKHOLM
        ).isoformat(),
        "n_train": len(train),
        "metrics": {
            "mae": float(mae),
            "r2": float(r2),
            "naive_mae": float(naive_mae),
        },
        "sklearn_version": __import__(
            "sklearn"
        ).__version__,
    }

    with MODEL_PATH.open("wb") as fh:
        pickle.dump(
            payload,
            fh,
        )

    print(
        f"\nwrote {MODEL_PATH}"
    )

    print(
        json.dumps(
            payload["metrics"],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()