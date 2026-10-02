import os
from datetime import UTC, datetime

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# 1757894400000 ms = 2025-09-15 00:00 UTC = 02:00 in Stockholm
ms = 1757894400000

naive = datetime.fromtimestamp(ms / 1000)                    # no timezone attached
aware = datetime.fromtimestamp(ms / 1000, tz=UTC)   # explicitly UTC

conn = psycopg2.connect(os.environ["DATABASE_URL"])
with conn.cursor() as cur:
    cur.execute("SHOW timezone")
    print("Supabase session timezone:", cur.fetchone()[0])
    print("Python naive value:       ", naive)
    print("Python aware value:       ", aware)
    print()

    cur.execute("CREATE TEMP TABLE t (label text, ts timestamptz)")
    cur.execute("INSERT INTO t VALUES ('naive', %s), ('aware', %s)", (naive, aware))
    cur.execute("""
        SELECT label,
               ts AT TIME ZONE 'UTC'              AS as_utc,
               ts AT TIME ZONE 'Europe/Stockholm' AS as_stockholm
        FROM t
    """)
    for label, utc, sthlm in cur.fetchall():
        print(f"{label:6}  UTC {utc}   Stockholm {sthlm}")
conn.close()