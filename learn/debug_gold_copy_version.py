import os

import pandas as pd
import psycopg2
from dotenv import load_dotenv
from features_copy_version import build_features, daily_prices, daily_weather

load_dotenv()

conn = psycopg2.connect(os.environ["DATABASE_URL"])

def fetch_df(sql, params):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)

prices = fetch_df(
    "SELECT starts_at, sek_per_kwh FROM learn.silver__elpris"
    " WHERE price_area = %(area)s ORDER BY starts_at",
    {"area": os.environ["PRICE_AREA"]},
)
weather = fetch_df(
    "SELECT parameter, observed_at, value, quality FROM learn.silver__weather"
    " WHERE station = %(station)s ORDER BY observed_at",
    {"station": os.environ["STATION_ID"]},
)
conn.close()

feat = build_features(daily_prices(prices), daily_weather(weather), "mean")

print("rows:", len(feat))

feat = feat.reset_index()
feat.insert(0, "price_area", os.environ["PRICE_AREA"])

SMALLINT_COLS = ["dayofweek", "month", "n_intervals", "n_obs_temp", "n_obs_wind"]

for col in SMALLINT_COLS:
    s = pd.to_numeric(feat[col], errors="coerce")
    out = feat[(s < -32768) | (s > 32767)]
    print(f"{col:14} dtype={feat[col].dtype}  out-of-range rows: {len(out)}")
    if len(out):
        print(out[["target_date", col]].head())

print("\ncolumns and dtypes actually being sent:")
print(feat.dtypes)

print("\nfirst row as a tuple:")
COLUMNS = [
    "price_area", "target_date",
    "tomorrow_temp_mean", "tomorrow_temp_min", "tomorrow_temp_max",
    "tomorrow_wind_mean", "price_today", "price_yesterday",
    "price_7d_ago", "price_7d_mean", "peak_today",
    "dayofweek", "month", "is_weekend",
    "n_intervals", "n_obs_temp", "n_obs_wind", "share_quality_g",
    "y",
]
row = next(feat[COLUMNS].itertuples(index=False))
for name, value in zip(COLUMNS, row, strict=True):
    print(f"  {name:20} {value!r:30} {type(value).__name__}")