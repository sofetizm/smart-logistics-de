import json
import os
from pathlib import Path
import psycopg

ROOT = Path(__file__).resolve().parents[1]
LOCK_ID = 899702


def connection_kwargs():
    if url := os.getenv("DATABASE_URL"):
        return {"conninfo": url}
    args = {}
    for env, key in [("PGHOST", "host"), ("PGPORT", "port"), ("PGUSER", "user"),
                     ("PGDATABASE", "dbname"), ("PGPASSWORD", "password")]:
        if os.getenv(env):
            args[key] = os.environ[env]
    if path := os.getenv("PASSWORD_FILE"):
        args["password"] = Path(path).read_text().strip()
    return args


def connect():
    return psycopg.connect(**connection_kwargs())


def log(event, **values):
    print(json.dumps({"event": event, **values}, default=str, ensure_ascii=False), flush=True)


def sql_file(name):
    return (ROOT / "sql" / name).read_text()


def initialize(conn):
    conn.execute(sql_file("001_dwh.sql"))


def execute_script(conn, name, params=None):
    with psycopg.ClientCursor(conn) as cur:
        cur.execute(sql_file(name), params)
