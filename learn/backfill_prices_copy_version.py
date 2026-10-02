"""
Backfill historical prices into Bronze, one day at a time.

Resumable: days already in learn.raw__elpris are skipped, so a crashed
run can simply be started again.

Run:  uv run python learn/backfill_prices_copy_version.py 2024-08-01 2026-09-22
"""
import os
import sys
import time
from datetime import date, timedelta

import psycopg2
from dotenv import load_dotenv
from ingest_copy_version import AREA, fetch_prices
from psycopg2.extras import Json

load_dotenv()

PAUSE_SECONDS = 1.0
COMMIT_EVERY = 30


def days_between(start, end):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def main():
    start = date.fromisoformat(sys.argv[1])
    end = date.fromisoformat(sys.argv[2])

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT price_date FROM learn.raw__elpris WHERE price_area = %s",
                (AREA,),
            )
            already = {row[0] for row in cur.fetchall()}

        todo = [d for d in days_between(start, end) if d not in already]
        print(f"{len(todo)} days to fetch, {len(already)} already in Bronze\n")

        inserted = not_found = 0
        with conn.cursor() as cur:
            for i, day in enumerate(todo, start=1):
                payload = fetch_prices(day)
                if payload is None:
                    not_found += 1
                    print(f"{day}: 404, skipped")
                else:
                    cur.execute(
                        "INSERT INTO learn.raw__elpris (price_area, price_date, data)"
                        " VALUES (%s, %s, %s)",
                        (AREA, day, Json(payload)),
                    )
                    inserted += 1

                if i % COMMIT_EVERY == 0:
                    conn.commit()
                    print(f"committed through {day}   ({i}/{len(todo)})")

                time.sleep(PAUSE_SECONDS)
        conn.commit()
    finally:
        conn.close()

    print(f"\ndone: {inserted} inserted, {not_found} not found")


if __name__ == "__main__":
    main()