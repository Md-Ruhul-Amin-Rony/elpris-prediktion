"""
Training pipeline: predict tomorrow's electricity price.

Reads prepared daily features from learn.feat__daily. Feature engineering
lives in features_copy_version.py and build_gold_copy_version.py; this file
only trains and evaluates.

Run:

    uv run python learn/train_copy_version.py

Configuration comes from the environment:

    PRICE_AREA         SE1 | SE2 | SE3 | SE4
    TARGET             mean | peak
    TRAIN_START_DATE   optional, defaults to the earliest row in Gold
    TRAIN_END_DATE     optional, defaults to the latest row in Gold
"""

from __future__ import annotations

import json
import os
import pickle
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.inspection import permutation_importance

from swedish_time_copy_version import STOCKHOLM

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(__file__).resolve().parent / "model_copy_version.pkl"

PRICE_AREA = os.getenv("PRICE_AREA", "SE3").upper()
TARGET = os.getenv("TARGET", "mean").lower()
TRAIN_START_DATE = os.getenv("TRAIN_START_DATE")
TRAIN_END_DATE = os.getenv("TRAIN_END_DATE")

# A year of data, so every month is represented at least once.
MIN_USABLE_ROWS = 365

RANDOM_SEED = 42
TEST_FRACTION = 0.2

# Bump when features_copy_version.py changes what a feature MEANS.
# A model trained on v1 features must not be fed v2 features.
FEATURE_VERSION = "v1"

# Typical error in a 24-hour temperature forecast, in degrees C.
# Used to estimate how the model would perform on forecasts rather
# than observations. See the information boundary in the README.
FORECAST_ERROR_C = 1.2

AREA_STATIONS = {
    "SE1": (162860, "Lulea-Kallax Flygplats"),
    "SE2": (134100, "Ostersunds Flygplats"),
    "SE3": (97400, "Stockholm-Arlanda Flygplats"),   # verified against SMHI
    "SE4": (53430, "Malmo A"),
}

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

# Temperature features stand in for a forecast, so they are the ones
# that would carry forecast error in production.
FORECAST_FEATURES = [
    "tomorrow_temp_mean",
    "tomorrow_temp_min",
    "tomorrow_temp_max",
]


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------
def get_git_sha() -> str:
    """SHA of the commit currently checked out, or 'unknown'."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, cwd=ROOT,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def make_model_version(area: str, target: str, trained_at: datetime, sha: str) -> str:
    """A human-readable identifier the predictions table can point at."""
    return f"{area}-{target}-{trained_at:%Y%m%d-%H%M}-{sha[:7]}"


# --------------------------------------------------------------------------
# database
# --------------------------------------------------------------------------
def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set. Add it to .env.")
    return psycopg2.connect(database_url)


def fetch_df(conn, sql: str, params: tuple) -> pd.DataFrame:
    """Run a query and return a DataFrame, without pandas' SQLAlchemy warning."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def load_features(area: str, start_date: str | None, end_date: str | None) -> pd.DataFrame:
    """Load prepared feature rows from Gold, oldest first."""
    sql = (
        f"SELECT target_date, {', '.join(FEATURES)}, y"
        " FROM learn.feat__daily"
        " WHERE price_area = %s"
        "   AND (%s::date IS NULL OR target_date >= %s::date)"
        "   AND (%s::date IS NULL OR target_date <= %s::date)"
        " ORDER BY target_date"
    )
    conn = get_connection()
    try:
        df = fetch_df(conn, sql, (area, start_date, start_date, end_date, end_date))
    finally:
        conn.close()

    if df.empty:
        raise SystemExit(f"No feature rows found for {area} in the given range.")

    # Postgres NUMERIC arrives as Decimal; sklearn needs floats.
    for col in FEATURES + ["y"]:
        if col != "is_weekend":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["is_weekend"] = df["is_weekend"].astype(int)

    df["target_date"] = pd.to_datetime(df["target_date"])
    return df.set_index("target_date")


# --------------------------------------------------------------------------
# train and evaluate
# --------------------------------------------------------------------------
def train_and_evaluate_model(
    area: str,
    start_date: str | None = None,
    end_date: str | None = None,
    verbose: bool = True,
) -> tuple[dict, pd.DataFrame]:
    """
    Train on the older part of the range and score on the newest 20%.

    Writes nothing to disk. The caller decides what happens to the result,
    so this can be called repeatedly for walk-forward validation.

    Returns:
        The model package and the holdout rows the metrics were measured on.

    Raises:
        SystemExit: if the range has no rows, or too few usable ones.
    """
    df = load_features(area, start_date, end_date)
    usable = df.dropna(subset=FEATURES + ["y"])

    if verbose:
        print(f"feature rows {len(df)} "
              f"({df.index.min().date()} .. {df.index.max().date()})")
        print(f"usable rows  {len(usable)} of {len(df)}")

    if len(usable) < MIN_USABLE_ROWS:
        raise SystemExit(
            f"Too few usable rows: {len(usable)}, need at least {MIN_USABLE_ROWS}. "
            "No model was trained."
        )

    # Chronological split: never shuffle a time series. Neighbouring days
    # share features, so a random split leaks the target across the boundary.
    cutoff = int(len(usable) * (1 - TEST_FRACTION))
    train, test = usable.iloc[:cutoff], usable.iloc[cutoff:]

    if train.empty or test.empty:
        raise SystemExit("Train/test split produced an empty dataset.")

    if verbose:
        print(f"train {len(train)} "
              f"({train.index.min().date()} .. {train.index.max().date()})")
        print(f"test  {len(test)} "
              f"({test.index.min().date()} .. {test.index.max().date()})")

    model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.06,
        max_depth=6,
        min_samples_leaf=15,
        l2_regularization=1.0,
        random_state=RANDOM_SEED,
    )
    model.fit(train[FEATURES], train["y"])

    pred = model.predict(test[FEATURES])
    mae = mean_absolute_error(test["y"], pred)
    r2 = r2_score(test["y"], pred)

    # Naive baseline: tomorrow is like today. Hard to beat, and the only
    # comparison that makes an MAE meaningful on its own.
    naive = test["price_today"] if TARGET == "mean" else test["peak_today"]
    naive_mae = mean_absolute_error(test["y"], naive)

    # Information boundary: in production the temperature features come from
    # a forecast, not observations. Re-score the same model on noisy inputs
    # to estimate how much of the measured performance is optimistic.
        # One random draw proves nothing on 155 test days. Average over
    # several, and report the spread so a small shift can be told
    # apart from noise.
    maes = []
    for seed in range(20):
        rng = np.random.default_rng(seed)
        noisy = test[FEATURES].copy()
        for col in FORECAST_FEATURES:
            noisy[col] = noisy[col] + rng.normal(0, FORECAST_ERROR_C, len(noisy))
        maes.append(mean_absolute_error(test["y"], model.predict(noisy)))

    forecast_mae = float(np.mean(maes))
    forecast_mae_sd = float(np.std(maes))
        # Which features is the model actually using? Shuffle each column
    # in turn and measure how much worse the predictions get.
    imp = permutation_importance(
        model, test[FEATURES], test["y"],
        n_repeats=20, random_state=RANDOM_SEED,
        scoring="neg_mean_absolute_error",
    )
    importance = dict(zip(FEATURES, (float(v) for v in imp.importances_mean)))

    if verbose:
        verdict = "beats" if mae < naive_mae else "LOSES TO"
        print()
        print(f"  MAE               {mae:.4f} SEK/kWh")
        print(f"  R2                {r2:.3f}")
        print(f"  naive MAE         {naive_mae:.4f} SEK/kWh  (tomorrow = today)")
        print(f"  model {verdict} the naive baseline "
              f"({(1 - mae / naive_mae) * 100:+.1f}%)")
        print(f"  MAE with {FORECAST_ERROR_C}C forecast error   "
              f"{forecast_mae:.4f} +/- {forecast_mae_sd:.4f} "
              f"({(forecast_mae / mae - 1) * 100:+.1f}%)")
        print("\n  feature importance (MAE increase when shuffled)")
        for name, value in sorted(importance.items(), key=lambda kv: -kv[1]):
            print(f"    {name:22} {value:+.4f}")

    trained_at = datetime.now(tz=STOCKHOLM)
    sha = get_git_sha()

    payload = {
        "model": model,
        "features": FEATURES,
        "price_area": area,
        "target": TARGET,

        # provenance
        "model_version": make_model_version(area, TARGET, trained_at, sha),
        "trained_at": trained_at.isoformat(),
        "git_sha": sha,
        "feature_version": FEATURE_VERSION,
        "seed": RANDOM_SEED,
        "sklearn_version": __import__("sklearn").__version__,

        # what it was trained on
        "n_feature_rows": len(df),
        "n_usable_rows": len(usable),
        "n_train": len(train),
        "n_test": len(test),
        "train_first_date": train.index.min().date().isoformat(),
        "train_last_date": train.index.max().date().isoformat(),
        "holdout_first_date": test.index.min().date().isoformat(),
        "holdout_last_date": test.index.max().date().isoformat(),

        "metrics": {
            "mae": float(mae),
            "r2": float(r2),
            "naive_mae": float(naive_mae),
            "mae_with_forecast_error": float(forecast_mae),
            "mae_with_forecast_error_sd": float(forecast_mae_sd),
        },
        "importance":importance,
    }
    return payload, test


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main() -> None:
    if TARGET not in ("mean", "peak"):
        raise SystemExit(f"TARGET must be 'mean' or 'peak', got {TARGET!r}")

    if PRICE_AREA not in AREA_STATIONS:
        raise SystemExit(
            f"Unknown PRICE_AREA {PRICE_AREA!r}. Use one of: {sorted(AREA_STATIONS)}"
        )

    print(f"area={PRICE_AREA}  target={TARGET}")

    payload, _ = train_and_evaluate_model(
        PRICE_AREA, TRAIN_START_DATE, TRAIN_END_DATE
    )

    with MODEL_PATH.open("wb") as fh:
        pickle.dump(payload, fh)

    print(f"\nwrote {MODEL_PATH}")
    print(f"model_version  {payload['model_version']}")
    print(json.dumps(payload["metrics"], indent=2))


if __name__ == "__main__":
    main()