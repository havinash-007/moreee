"""Tiny SQLite layer (stdlib only). One file, no server. Used for Full-auto jobs; swap for Postgres when hosting at scale."""
import sqlite3
import threading
from pathlib import Path

from . import config

PATH = config.DATA / "jobs.db"
_ready: set[str] = set()
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, user TEXT NOT NULL, repo TEXT NOT NULL, number INTEGER NOT NULL, title TEXT NOT NULL,
  status TEXT NOT NULL, stage TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL,
  token_hash TEXT NOT NULL, signoff INTEGER NOT NULL DEFAULT 0, legal TEXT NOT NULL DEFAULT '[]',
  result TEXT NOT NULL DEFAULT '{}', pr_title TEXT NOT NULL DEFAULT '', pr_body TEXT NOT NULL DEFAULT '',
  pr_url TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '', warnings TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS jobs_user ON jobs(user, created);
CREATE TABLE IF NOT EXISTS profiles (
  user TEXT PRIMARY KEY, answers TEXT NOT NULL DEFAULT '{}', settings TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL, updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, ts REAL NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_job ON events(job_id, id);
"""


def connect() -> sqlite3.Connection:
    path = Path(PATH)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    with _lock:
        if str(path) not in _ready:
            con.executescript(SCHEMA)
            con.commit()
            _ready.add(str(path))
    return con
