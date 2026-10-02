"""
Validation: compare what Silver holds with what the calendar says it should hold.

Reports problems. Never changes data.
Exits with code 1 if something needs attention now, 0 otherwise.

Run:  uv run python learn/validate_copy_version.py 2024-08-01
"""
import os
import sys
from datetime import date, datetime, timedelta

import psycopg2
from dotenv import load_dotenv
from swedish_time_copy_version import (
    STOCKHOLM,
    expected_price_intervals,
    expected_weather_readings,
)

load_dotenv()

AREA = os.environ["PRICE_AREA"]
STATION = os.environ["STATION_ID"]
RECENT_DAYS = 2   # problems in the last N complete days fail the run

WEATHER_RANGE = {"temperature": (-45, 40), "wind": (0, 50)}
PRICE_RANGE = (-5, 30)


def all_days(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: validate_copy_version.py <first-date YYYY-MM-DD>")

    start = date.fromisoformat(sys.argv[1])
    end = datetime.now(STOCKHOLM).date() - timedelta(days=1)   # last complete day
    recent_from = end - timedelta(days=RECENT_DAYS - 1)
    days = list(all_days(start, end))

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:

            # --- what is actually there ---------------------------------
            cur.execute(
                "SELECT price_date, count(*) FROM learn.silver__elpris"
                " WHERE price_area = %s GROUP BY price_date",
                (AREA,),
            )
            price_counts = dict(cur.fetchall())

            cur.execute(
                "SELECT parameter,"
                "       (observed_at AT TIME ZONE 'Europe/Stockholm')::date,"
                "       count(*)"
                " FROM learn.silver__weather WHERE station = %s"
                " GROUP BY 1, 2",
                (STATION,),
            )
            weather_counts = {(p, d): n for p, d, n in cur.fetchall()}

            # --- structure: must never break ----------------------------
            cur.execute(
                "SELECT count(*) - count(DISTINCT (price_area, starts_at))"
                " FROM learn.silver__elpris"
            )
            price_dupes = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) - count(DISTINCT (station, parameter, observed_at))"
                " FROM learn.silver__weather"
            )
            weather_dupes = cur.fetchone()[0]

            # --- plausibility: odd, not necessarily wrong ---------------
            plausibility = {}
            for name, (lo, hi) in WEATHER_RANGE.items():
                cur.execute(
                    "SELECT count(*) FILTER (WHERE value IS NULL),"
                    "       count(*) FILTER (WHERE value < %s OR value > %s)"
                    " FROM learn.silver__weather"
                    " WHERE station = %s AND parameter = %s",
                    (lo, hi, STATION, name),
                )
                plausibility[name] = cur.fetchone()

            lo, hi = PRICE_RANGE
            cur.execute(
                "SELECT count(*) FILTER (WHERE sek_per_kwh IS NULL),"
                "       count(*) FILTER (WHERE sek_per_kwh < %s OR sek_per_kwh > %s)"
                " FROM learn.silver__elpris WHERE price_area = %s",
                (lo, hi, AREA),
            )
            plausibility["prices"] = cur.fetchone()
    finally:
        conn.close()

    # --- compare every day with the calendar --------------------------
    problems = []
    summary = {}
    for name in ["prices", *WEATHER_RANGE]:
        complete = 0
        missing = 0
        for day in days:
            if name == "prices":
                expected = expected_price_intervals(day)
                found = price_counts.get(day, 0)
            else:
                expected = expected_weather_readings(day)
                found = weather_counts.get((name, day), 0)

            if found == expected:
                complete += 1
            else:
                problems.append((day, name, expected, found))
                missing += expected - found
        summary[name] = (complete, missing)

    # --- report --------------------------------------------------------
    print(f"Validating {start} .. {end}  ({len(days)} days)\n")

    print("Completeness")
    for name, (complete, missing) in summary.items():
        unit = "intervals" if name == "prices" else "readings"
        print(f"  {name:12} {complete}/{len(days)} days complete, {missing} {unit} missing")

    if problems:
        print("\nDays that don't match the calendar")
        for day, name, expected, found in sorted(problems):
            print(f"  {day}  {name:12} expected {expected:>3}  found {found:>3}"
                  f"  ({found - expected:+d})")

    print("\nStructure (must always be 0)")
    print(f"  duplicate price intervals   {price_dupes}")
    print(f"  duplicate weather readings  {weather_dupes}")

    print("\nPlausibility (worth a look, not necessarily wrong)")
    for name, (nulls, outside) in plausibility.items():
        lo, hi = PRICE_RANGE if name == "prices" else WEATHER_RANGE[name]
        print(f"  {name:12} {nulls} null, {outside} outside {lo}..{hi}")

    print()
    recent = [p for p in problems if p[0] >= recent_from]
    if recent or price_dupes or weather_dupes:
        print(f"FAIL: problems in the last {RECENT_DAYS} days, or broken structure")
        sys.exit(1)
    print(f"OK: last {RECENT_DAYS} days complete, structure intact")


if __name__ == "__main__":
    main()