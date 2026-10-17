"""Hand-built cases for Swedish calendar math. No database."""

from datetime import date

from swedish_time_copy_version import (
    expected_price_intervals,
    expected_weather_readings,
    hours_in_local_day,
)


def test_normal_day_has_24_hours():
    assert hours_in_local_day(date(2026, 1, 15)) == 24


def test_dst_start_day_has_23_hours():
    # Last Sunday of March: 02:00 becomes 03:00, one hour never happens.
    assert hours_in_local_day(date(2026, 3, 29)) == 23


def test_dst_end_day_has_25_hours():
    # Last Sunday of October: 03:00 becomes 02:00, one hour happens twice.
    assert hours_in_local_day(date(2026, 10, 25)) == 25


def test_hourly_prices_before_october_2025():
    assert expected_price_intervals(date(2025, 9, 30)) == 24


def test_quarter_hour_prices_from_october_2025():
    assert expected_price_intervals(date(2025, 10, 1)) == 96


def test_quarter_hour_prices_on_dst_end_day():
    # Last Sunday of October 2025: 25 local hours x 4 intervals.
    # A hard-coded 96 would flag this normal, longer day as wrong.
    assert expected_price_intervals(date(2025, 10, 26)) == 100


def test_expected_weather_readings_matches_hours_in_day():
    assert expected_weather_readings(date(2026, 3, 29)) == 23
