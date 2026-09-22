"""Run a SQL file against the database.  Usage: run_sql_copy_version.py <file.sql>"""
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    sql = fh.read()

conn = psycopg2.connect(os.environ["DATABASE_URL"])
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
finally:
    conn.close()

print(f"ran {path}")