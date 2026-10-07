"""Postgres-only behaviour (skipped when no local Postgres binaries are available; CI can set PG_BIN or run a service container)."""
import threading
import time

import pytest

from backend import auth, config, db, jobs, replier, usage

pytestmark = pytest.mark.usefixtures("pg_url")


@pytest.fixture
def pg(pg_url, monkeypatch):
    if not pg_url:
        pytest.skip("no local PostgreSQL available")
    monkeypatch.setattr(config, "DATABASE_URL", pg_url)
    db._ready.clear()
    db.reset_for_tests()
    auth._epoch_cache.clear()
    return pg_url


def test_backend_selection_and_row_semantics(pg):
    assert db.backend() == "postgres"
    with db.connect() as con:
        con.execute("INSERT INTO profiles(uid, answers, settings, created, updated) VALUES (?,?,?,?,?)", ("u", "{}", "{}", 1.0, 2.0))
        r = con.execute("SELECT uid, created FROM profiles WHERE uid=?", ("u",)).fetchone()
        assert r["uid"] == "u" and r[0] == "u" and r[1] == 1.0 and dict(r) == {"uid": "u", "created": 1.0} and list(r.keys()) == ["uid", "created"]
        assert con.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 1
        assert con.execute("SELECT * FROM profiles WHERE uid=?", ("nobody",)).fetchone() is None


def test_timestamps_keep_full_precision(pg):
    t = 1791358765.123456
    with db.connect() as con:
        con.execute("INSERT INTO auth_epoch(uid, epoch) VALUES (?,?)", ("p", t))
    assert auth.epoch("p") == t            # a 4-byte REAL would have rounded this to the nearest 128 seconds


def test_schema_creation_is_idempotent_and_survives_a_cold_start(pg):
    db._ready.clear()
    with db.connect() as c1:
        c1.execute("SELECT 1")
    db._ready.clear()                      # a second serverless instance running the same CREATE IF NOT EXISTS
    with db.connect() as c2:
        assert c2.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_concurrent_spend_never_loses_money(pg):
    """Many serverless instances charging the same student at once: the budget must add up exactly."""
    errs = []
    def worker():
        try:
            for _ in range(5): usage.add("alice", 0.01, 10, 5)
        except Exception as e: errs.append(e)
    ts = [threading.Thread(target=worker) for _ in range(16)]
    [t.start() for t in ts]; [t.join() for t in ts]
    s = usage.summary("alice")
    assert not errs and s["calls"] == 80 and abs(s["cost_usd"] - 0.80) < 1e-9 and s["input_tokens"] == 800
    assert abs(usage.today_all() - 0.80) < 1e-9 and usage.today("bob") == 0


def test_daily_window_rolls_over(pg, monkeypatch):
    usage.add("alice", 0.4, 1, 1)
    monkeypatch.setattr(usage, "day", lambda: "2099-01-02")
    assert usage.today("alice") == 0       # tomorrow starts fresh
    monkeypatch.setattr(usage, "day", lambda: usage.datetime.now(usage.timezone.utc).strftime("%Y-%m-%d"))
    assert usage.today("alice") == 0.4


def test_concurrent_job_events_get_unique_increasing_ids(pg, monkeypatch):
    monkeypatch.setattr(jobs.github, "policy_scan", lambda o, r: {"files": [], "ai_flags": [], "legal": []})
    monkeypatch.setattr(jobs.github, "verify_issue", lambda *a, **k: {"ok": True, "reason": "", "checked_at": "t", "linked_prs": []})
    j = jobs.create("alice", "acme/widgets", 7, "T", True, False)
    def w(n):
        for i in range(10): jobs.runner_event(j["id"], j["token"], "w", f"{n}-{i}")
    ts = [threading.Thread(target=w, args=(n,)) for n in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    ids = [e["id"] for e in jobs.get("alice", j["id"])["events"]]
    assert len(ids) == 61 and len(set(ids)) == 61 and ids == sorted(ids)


def test_reply_state_upserts_per_student(pg):
    replier._mark("alice", "o/r#1", [3]); replier._mark("alice", "o/r#1", [5, 3]); replier._mark("bob", "o/r#1", [9])
    assert replier._handled("alice", "o/r#1") == {3, 5} and replier._handled("bob", "o/r#1") == {9} and replier._handled("carol", "o/r#1") == set()


def test_revocation_is_visible_to_a_second_connection(pg, monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", "k" * 40); monkeypatch.setattr(auth, "EPOCH_TTL", 0)
    u = auth.User("alice", "tok"); c = auth.seal(u)
    class R: cookies = {auth.COOKIE: c}
    assert auth._session(R()) is not None
    auth.revoke("alice")
    assert auth._session(R()) is None
    time.sleep(0.01)
    c2 = auth.seal(auth.User("alice", "tok")); R.cookies = {auth.COOKIE: c2}
    assert auth._session(R()) is not None
