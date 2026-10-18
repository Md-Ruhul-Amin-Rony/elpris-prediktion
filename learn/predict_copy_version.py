"""
Predict from the current champion and log the prediction with full
traceability (component D): which data, which model, which code, when.

Predicts whichever row is not resolved yet (feat__daily.y IS NULL) --
not a fixed "tomorrow", since the day-ahead price market can already
have published the next day's price by the time this runs. See
docs/validation.md for why that is not a bug.

Run:  uv run python learn/predict_copy_version.py
"""
import os
import pickle

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from huggingface_hub import HfApi, hf_hub_download
from psycopg2.extras import Json
from train_copy_version import FEATURES

load_dotenv()

# os.getenv, not os.environ[...]: this module is imported by tests for its
# pure functions (is_weather_forecast, build_feature_snapshot), which don't
# need any of this -- a hard KeyError here would fail that import in any
# environment without PRICE_AREA set (e.g. CI's lint/test job, which has no
# .env and no reason to need one). main() checks AREA itself before using it.
AREA = os.getenv("PRICE_AREA")
TARGET = os.getenv("TARGET", "mean")
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL_REPO = os.getenv("HF_MODEL_REPO")
HF_MODEL_FILENAME = "model.pkl"


def load_champion() -> tuple[dict, str]:
    """Download the current champion and the exact Hub revision it came from."""
    if not HF_MODEL_REPO:
        raise SystemExit("HF_MODEL_REPO is not set -- no champion to predict from.")

    api = HfApi(token=HF_TOKEN)
    model_revision = api.model_info(HF_MODEL_REPO).sha

    path = hf_hub_download(
        repo_id=HF_MODEL_REPO, filename=HF_MODEL_FILENAME, token=HF_TOKEN,
    )
    with open(path, "rb") as fh:
        payload = pickle.load(fh)

    return payload, model_revision


def load_unresolved_row(conn, area: str) -> pd.Series:
    """The oldest row whose price is not known yet."""
    query = (
        f"SELECT target_date, {', '.join(FEATURES)}, n_obs_temp, n_obs_wind, built_at"
        " FROM learn.feat__daily"
        " WHERE price_area = %s AND y IS NULL"
        " ORDER BY target_date"
        " LIMIT 1"
    )
    df = pd.read_sql_query(query, conn, params=(area,))
    if df.empty:
        raise SystemExit(f"No unresolved row to predict for {area}.")
    return df.iloc[0]


def is_weather_forecast(row: pd.Series) -> bool:
    """True if this row's weather came from a forecast, not a measurement.

    Either count being exactly 0 means that variable has zero real hours
    behind it -- see fill_forecast_gaps in features_copy_version.py.
    """
    return bool(row["n_obs_temp"] == 0 or row["n_obs_wind"] == 0)


def build_feature_snapshot(row: pd.Series, features: list[str]) -> dict:
    """The exact feature values fed to the model, frozen for traceability.

    feat__daily is overwritten nightly (forecast weather becomes real
    observed weather once the day passes), so without this snapshot
    "which data was this prediction built on" becomes unanswerable within
    a day or two of asking.
    """
    return {col: (None if pd.isna(row[col]) else float(row[col])) for col in features}


def main() -> None:
    if not AREA:
        raise SystemExit("PRICE_AREA is not set.")

    payload, model_revision = load_champion()
    model = payload["model"]

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        row = load_unresolved_row(conn, AREA)

        x = pd.DataFrame([row[FEATURES].astype(float)], columns=FEATURES)
        predicted_value = float(model.predict(x)[0])

        weather_is_forecast = is_weather_forecast(row)
        feature_snapshot = build_feature_snapshot(row, FEATURES)

        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learn.predictions (
                    price_area, target_date, target, predicted_value,
                    feature_snapshot, weather_is_forecast, feature_built_at,
                    model_version, feature_version, model_revision, git_sha
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    AREA, row["target_date"], TARGET, predicted_value,
                    Json(feature_snapshot), weather_is_forecast, row["built_at"],
                    payload["model_version"], payload["feature_version"],
                    model_revision, payload["git_sha"],
                ),
            )
    finally:
        conn.close()

    print(
        f"predicted {AREA} {row['target_date']} {TARGET} = {predicted_value:.4f}"
        f" (model {payload['model_version']}, weather_is_forecast={weather_is_forecast})"
    )


if __name__ == "__main__":
    main()
