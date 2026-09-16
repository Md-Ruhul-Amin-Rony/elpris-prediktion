"""Hand-built cases for the validation logic. No database."""

from datetime import date

from validate import (
    compare_counts,
    expected_price_intervals,
    expected_prices,
    expected_weather,
    hours_in_local_day,
    window_days,
)


def test_normal_day_has_24_hours():
    assert hours_in_local_day(date(2026, 9, 1)) == 24


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
    # 25 local hours x 4 intervals. A hard-coded 96 would flag a normal day.
    assert expected_price_intervals(date(2025, 10, 26)) == 100


def test_compare_all_present_is_ok():
    result = compare_counts(
        {"2026-09-01": 96, "2026-09-02": 96}, {"2026-09-01": 96, "2026-09-02": 96}
    )
    assert result.ok is True
    assert (result.expected, result.found) == (192, 192)
    assert result.details == {}


def test_compare_absent_day_counts_as_zero():
    # No row at all must not be silent: it is the most common real failure.
    result = compare_counts({"2026-09-01": 96, "2026-09-02": 96}, {"2026-09-01": 96})
    assert result.ok is False
    assert result.found == 96
    assert result.details == {"2026-09-02": 0}


def test_compare_partial_day_reports_found_count():
    result = compare_counts({"2026-09-01/wind": 24}, {"2026-09-01/wind": 22})
    assert result.details == {"2026-09-01/wind": 22}
    assert (result.expected, result.found) == (24, 22)


def test_compare_surplus_is_also_reported():
    # "Nothing silently added": more rows than expected is a difference too.
    result = compare_counts({"2026-09-01": 24}, {"2026-09-01": 25})
    assert result.ok is False
    assert result.details == {"2026-09-01": 25}


def test_window_is_complete_days_ending_yesterday():
    # Same rule as daily_ingest.py: today is excluded, it is not complete yet.
    days = window_days(today=date(2026, 9, 3), days=7)
    assert days[0] == date(2026, 8, 27)
    assert days[-1] == date(2026, 9, 2)
    assert len(days) == 7


def test_expected_prices_keyed_by_day():
    assert expected_prices([date(2026, 9, 1)]) == {"2026-09-01": 96}


def test_expected_weather_keyed_by_day_and_parameter():
    assert expected_weather([date(2026, 9, 1)], ("temperature", "wind")) == {
        "2026-09-01/temperature": 24,
        "2026-09-01/wind": 24,
    }
