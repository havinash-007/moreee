"""Tiny database layer with two backends behind one interface.

  SQLite   : local development (one file, zero setup).
  Postgres : whenever DATABASE_URL is set; required on serverless hosts such as Vercel, where nothing else survives between requests.
SQL is written once with `?` placeholders; the Postgres wrapper translates them. Rows work by name and by index on both backends.
"""
import sqlite3
import threading
from pathlib import Path

from . import config

PATH = config.DATA / "jobs.db"
_ready: set[str] = set()
_lock = threading.Lock()

_TABLES = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, uid TEXT NOT NULL, repo TEXT NOT NULL, number INTEGER NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL, stage TEXT NOT NULL DEFAULT '', created {REAL} NOT NULL, updated {REAL} NOT NULL,
  token_hash TEXT NOT NULL, signoff INTEGER NOT NULL DEFAULT 0, legal TEXT NOT NULL DEFAULT '[]',
  result TEXT NOT NULL DEFAULT '{{}}', pr_title TEXT NOT NULL DEFAULT '', pr_body TEXT NOT NULL DEFAULT '',
  pr_url TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '', warnings TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS jobs_uid ON jobs(uid, created);
CREATE TABLE IF NOT EXISTS profiles (
  uid TEXT PRIMARY KEY, answers TEXT NOT NULL DEFAULT '{{}}', settings TEXT NOT NULL DEFAULT '{{}}', created {REAL} NOT NULL, updated {REAL} NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id {AUTOID}, job_id TEXT NOT NULL, ts {REAL} NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job ON events(job_id, id);
CREATE TABLE IF NOT EXISTS usage (
  uid TEXT NOT NULL, day TEXT NOT NULL, cost {REAL} NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0,
  input_tokens BIGINT NOT NULL DEFAULT 0, output_tokens BIGINT NOT NULL DEFAULT 0, PRIMARY KEY (uid, day)
);
CREATE TABLE IF NOT EXISTS reply_state (
  uid TEXT NOT NULL, pr TEXT NOT NULL, handled TEXT NOT NULL DEFAULT '[]', PRIMARY KEY (uid, pr)
);
CREATE TABLE IF NOT EXISTS auth_epoch (uid TEXT PRIMARY KEY, epoch {REAL} NOT NULL);
"""
TABLE_NAMES = ("jobs", "profiles", "events", "usage", "reply_state", "auth_epoch")


def backend() -> str:
    return "postgres" if config.DATABASE_URL else "sqlite"


class Row(tuple):
    """Postgres row that behaves like sqlite3.Row: row['name'], row[0], dict(row)."""
    def __new__(cls, cols, values):
        r = super().__new__(cls, values)
        r._cols = list(cols)
        return r

    def __getitem__(self, k):
        return super().__getitem__(self._cols.index(k) if isinstance(k, str) else k)

    def keys(self):
        return list(self._cols)


def _pg_row_factory(cursor):
    cols = [d.name for d in cursor.description] if cursor.description else []
    return lambda values: Row(cols, values)


class Conn:
    """execute(sql, params) with `?` placeholders; `with` commits on success, rolls back on error, always closes."""
    def __init__(self, raw, pg: bool):
        self._c, self._pg = raw, pg

    def execute(self, sql: str, params=()):
        return self._c.execute(sql.replace("?", "%s") if self._pg else sql, tuple(params))

    def commit(self):
        self._c.commit()

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        try:
            self._c.rollback() if et else self._c.commit()
        finally:
            self._c.close()


def schema_sql(pg: bool) -> list[str]:
    sql = _TABLES.format(REAL="DOUBLE PRECISION" if pg else "REAL", AUTOID="BIGSERIAL PRIMARY KEY" if pg else "INTEGER PRIMARY KEY AUTOINCREMENT")
    return [x.strip() for x in sql.split(";") if x.strip()]


def connect() -> Conn:
    if config.DATABASE_URL:
        import psycopg
        raw = psycopg.connect(config.DATABASE_URL, row_factory=_pg_row_factory, connect_timeout=10)
        key = "pg:" + config.DATABASE_URL
        with _lock:
            if key not in _ready:
                for stmt in schema_sql(True):
                    raw.execute(stmt)
                raw.commit()
                _ready.add(key)
        return Conn(raw, True)
    path = Path(PATH)
    raw = sqlite3.connect(path, timeout=15)
    raw.row_factory = sqlite3.Row
    with _lock:
        if str(path) not in _ready:
            for stmt in schema_sql(False):
                raw.execute(stmt)
            raw.commit()
            _ready.add(str(path))
    return Conn(raw, False)


def reset_for_tests() -> None:
    """Empty every table (tests only)."""
    with connect() as con:
        for t in TABLE_NAMES:
            con.execute(f"DELETE FROM {t}")
