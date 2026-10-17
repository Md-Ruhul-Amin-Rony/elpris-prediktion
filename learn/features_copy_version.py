"""
Turn Silver's hourly data into one row per day we want to predict.

Pure functions over DataFrames: no database, no network.
"""
import pandas as pd
from swedish_time_copy_version import STOCKHOLM

MAX_GAP_HOURS = 6


def daily_prices(prices):
    """One row per Swedish calendar day, from interval-level prices."""
    df = prices.copy()
    df["ts"] = pd.to_datetime(df["starts_at"], utc=True).dt.tz_convert(STOCKHOLM)
    df["day"] = df["ts"].dt.date
    df["sek_per_kwh"] = pd.to_numeric(df["sek_per_kwh"])

    grouped = df.groupby("day")["sek_per_kwh"]
    daily = pd.DataFrame({
        "mean_price": grouped.mean(),
        "peak_price": grouped.max(),
        "n_intervals": grouped.size(),
    })
    daily.index = pd.to_datetime(daily.index)
    return daily.sort_index()


def daily_weather(weather):
    """One row per Swedish day, after filling short gaps."""
    df = weather.copy()
    df["ts"] = pd.to_datetime(df["observed_at"], utc=True)
    df["value"] = pd.to_numeric(df["value"])

    wide = df.pivot_table(index="ts", columns="parameter", values="value")
    quality_g = (
        df[df["parameter"] == "temperature"]
        .set_index("ts")["quality"]
        .eq("G")
    )

    # Count real readings per Swedish day, BEFORE filling anything.
    local_day = wide.index.tz_convert(STOCKHOLM).date
    real_counts = wide.notna().groupby(local_day).sum()

    # Put every expected hour on the index, then fill short gaps only.
    full_hours = pd.date_range(wide.index.min(), wide.index.max(), freq="h", tz="UTC")
    wide = wide.reindex(full_hours)
    wide = wide.interpolate(method="time", limit=MAX_GAP_HOURS, limit_area="inside")

    wide["day"] = wide.index.tz_convert(STOCKHOLM).date
    grouped = wide.groupby("day")

    daily = pd.DataFrame({
        "temp_mean": grouped["temperature"].mean(),
        "temp_min": grouped["temperature"].min(),
        "temp_max": grouped["temperature"].max(),
        "wind_mean": grouped["wind"].mean(),
    })
    daily["n_obs_temp"] = real_counts["temperature"]
    daily["n_obs_wind"] = real_counts["wind"]
    daily["share_quality_g"] = quality_g.groupby(
        quality_g.index.tz_convert(STOCKHOLM).date
    ).mean().round(4)

    daily.index = pd.to_datetime(daily.index)
    return daily.sort_index()


def daily_forecast(forecast):
    """One row per Swedish day the forecast covers. Same shape as daily_weather()."""
    df = forecast.copy()
    df["value"] = pd.to_numeric(df["value"])
    df["ts"] = pd.to_datetime(df["valid_at"], utc=True)

    wide = df.pivot_table(index="ts", columns="parameter", values="value")
    wide["day"] = wide.index.tz_convert(STOCKHOLM).date
    grouped = wide.groupby("day")

    daily = pd.DataFrame({
        "temp_mean": grouped["temperature"].mean(),
        "temp_min": grouped["temperature"].min(),
        "temp_max": grouped["temperature"].max(),
        "wind_mean": grouped["wind"].mean(),
    })
    daily.index = pd.to_datetime(daily.index)
    return daily.sort_index()


# Which feat__daily column a forecast day's aggregate fills, when real
# observations haven't happened yet -- and which n_obs column must become
# 0 (a known fact: zero real hours), not stay NULL (unknown), when it does.
FORECAST_FILL_COLUMNS = {
    "tomorrow_temp_mean": ("temp_mean", "n_obs_temp"),
    "tomorrow_temp_min": ("temp_min", "n_obs_temp"),
    "tomorrow_temp_max": ("temp_max", "n_obs_temp"),
    "tomorrow_wind_mean": ("wind_mean", "n_obs_wind"),
}


def fill_forecast_gaps(feat, forecast):
    """
    Fill NULL tomorrow_* weather -- the row not yet observed -- from a forecast.

    Only touches cells build_features() left NULL. Every historical row
    already has its real observed "tomorrow" from the shift, and keeps it
    untouched here. A filled row's matching n_obs_temp/n_obs_wind also
    becomes 0 rather than staying NULL: a forecast-filled day genuinely has
    zero real observed hours, and that is the signal that later tells a
    forecast-filled row apart from an ordinary observation gap. Returns
    (filled, n_filled) so the caller can report how many values came from
    a forecast rather than a measurement.
    """
    filled = feat.copy()
    n_filled = 0

    if forecast.empty:
        return filled, n_filled

    daily = daily_forecast(forecast)

    for feat_col, (forecast_col, n_obs_col) in FORECAST_FILL_COLUMNS.items():
        missing = filled.index[filled[feat_col].isna()]
        for target_date in missing:
            if target_date not in daily.index:
                continue
            value = daily.loc[target_date, forecast_col]
            if pd.notna(value):
                filled.loc[target_date, feat_col] = value
                if pd.isna(filled.loc[target_date, n_obs_col]):
                    filled.loc[target_date, n_obs_col] = 0
                n_filled += 1

    return filled, n_filled


def build_features(daily_price, daily_weather_df, target="mean"):
    """
    One row per PREDICTION DAY.

    The index is day D while we build. Everything named `tomorrow_*`
    and `y` refers to D+1. At the end we relabel the index to D+1,
    so each stored row is keyed by the day it predicts.
    """
    df = daily_price.join(daily_weather_df, how="left")

    # --- known at prediction time: day D and earlier -------------------
    df["price_today"] = df["mean_price"]
    df["price_yesterday"] = df["mean_price"].shift(1)
    df["price_7d_ago"] = df["mean_price"].shift(7)
    df["price_7d_mean"] = df["mean_price"].rolling(7, min_periods=3).mean()
    df["peak_today"] = df["peak_price"]

    # --- from day D+1: forecast stand-ins, and the answer --------------
    df["tomorrow_temp_mean"] = df["temp_mean"].shift(-1)
    df["tomorrow_temp_min"] = df["temp_min"].shift(-1)
    df["tomorrow_temp_max"] = df["temp_max"].shift(-1)
    df["tomorrow_wind_mean"] = df["wind_mean"].shift(-1)
    df["n_obs_temp"] = df["n_obs_temp"].shift(-1)
    df["n_obs_wind"] = df["n_obs_wind"].shift(-1)
    df["share_quality_g"] = df["share_quality_g"].shift(-1)
    df["y"] = (df["mean_price"] if target == "mean" else df["peak_price"]).shift(-1)

    # --- calendar facts about D+1 --------------------------------------
    tomorrow = df.index + pd.Timedelta(days=1)
    df["dayofweek"] = tomorrow.dayofweek
    df["month"] = tomorrow.month
    df["is_weekend"] = tomorrow.dayofweek >= 5

    # --- relabel: this row is ABOUT the day it predicts -----------------
    df.index = tomorrow
    df.index.name = "target_date"

    return df[[
        "tomorrow_temp_mean", "tomorrow_temp_min", "tomorrow_temp_max",
        "tomorrow_wind_mean", "price_today", "price_yesterday",
        "price_7d_ago", "price_7d_mean", "peak_today",
        "dayofweek", "month", "is_weekend",
        "n_intervals", "n_obs_temp", "n_obs_wind", "share_quality_g",
        "y",
    ]]