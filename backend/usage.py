"""Per-student spend, kept in the database so budgets hold across serverless instances and restarts.
With no DATABASE_URL (local use) llm.py keeps its in-memory ledger instead and this module stays idle.
In database mode the budget window is one UTC day per student."""
from datetime import datetime, timezone

from . import config, db


def persistent() -> bool:
    return bool(config.DATABASE_URL)


def day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def today(uid: str) -> float:
    with db.connect() as con:
        r = con.execute("SELECT cost FROM usage WHERE uid=? AND day=?", (uid, day())).fetchone()
    return float(r[0]) if r else 0.0


def today_all() -> float:
    with db.connect() as con:
        return float(con.execute("SELECT COALESCE(SUM(cost), 0) FROM usage WHERE day=?", (day(),)).fetchone()[0])


def add(uid: str, cost: float, inp: int, out: int) -> None:
    with db.connect() as con:
        con.execute("INSERT INTO usage(uid, day, cost, calls, input_tokens, output_tokens) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(uid, day) DO UPDATE SET cost=usage.cost+excluded.cost, calls=usage.calls+1, "
                    "input_tokens=usage.input_tokens+excluded.input_tokens, output_tokens=usage.output_tokens+excluded.output_tokens",
                    (uid, day(), cost, 1, inp, out))


def summary(uid: str) -> dict:
    with db.connect() as con:
        r = con.execute("SELECT cost, calls, input_tokens, output_tokens FROM usage WHERE uid=? AND day=?", (uid, day())).fetchone()
    cost, calls, i, o = (float(r[0]), int(r[1]), int(r[2]), int(r[3])) if r else (0.0, 0, 0, 0)
    return {"input_tokens": i, "output_tokens": o, "cache_read_tokens": 0, "cache_write_tokens": 0, "cost_usd": round(cost, 6), "calls": calls, "cache_hits": 0}


def delete(uid: str) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM usage WHERE uid=?", (uid,))
