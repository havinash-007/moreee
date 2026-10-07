"""Properties a PUBLIC serverless deployment must have: it refuses to serve until safely configured, sessions are stateless and
revocable, budgets persist, and nothing relies on a writable disk."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from backend import auth, catalogue, config, db, jobs, llm, profiles, usage
from backend.app import app

KEY = "k" * 40


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(db, "PATH", tmp_path / "d.db"); db._ready.clear()
    auth._epoch_cache.clear(); auth.SESSIONS.clear()
    return tmp_path


def public(monkeypatch, *, oauth=True, key=True, dburl=True):
    monkeypatch.setattr(config, "PUBLIC_DEPLOY", True)
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "id" if oauth else "")
    monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "s" if oauth else "")
    monkeypatch.setattr(config, "SECRET_KEY", KEY if key else "")
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://x/y" if dburl else "")
    monkeypatch.setattr(config, "BASE_URL", "http://testserver")


# ------------------------------------------------------------------ the guard
def test_unconfigured_public_deploy_serves_no_api(monkeypatch):
    public(monkeypatch, oauth=False, key=False, dburl=False)
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200                       # health is allowed and says what is missing
    h = c.get("/api/health").json()
    assert h["configured"] is False and len(h["missing"]) == 3 and h["public_deploy"] is True
    for path in ("/api/orgs", "/api/questions", "/api/catalogue/status", "/api/me", "/api/profile", "/api/usage", "/auth/login"):
        r = c.get(path)
        assert r.status_code == 503 and r.json()["kind"] == "setup" and r.json()["missing"], path
    for path in ("/api/match", "/api/scout", "/api/scout/stream", "/api/tour", "/api/coach", "/api/jobs"):
        assert c.post(path, json={}).status_code == 503, path
    assert c.get("/").status_code == 200                                   # the page itself loads, to show setup instructions


@pytest.mark.parametrize("missing", ["oauth", "key", "dburl"])
def test_every_single_missing_piece_blocks_the_api(monkeypatch, missing):
    public(monkeypatch, **{missing: False})
    r = TestClient(app).get("/api/questions")
    assert r.status_code == 503 and len(r.json()["missing"]) == 1


def test_short_secret_key_is_rejected(monkeypatch):
    public(monkeypatch)
    monkeypatch.setattr(config, "SECRET_KEY", "short")
    assert TestClient(app).get("/api/questions").status_code == 503


def test_fully_configured_public_deploy_requires_sign_in(monkeypatch):
    public(monkeypatch)
    c = TestClient(app)
    assert c.get("/api/health").json()["configured"] is True
    assert c.get("/api/questions").status_code == 200
    assert c.get("/api/profile").status_code == 401                        # configured, so now it asks for sign-in
    assert c.post("/api/scout", json={"org": "x", "profile": {}}).status_code == 401


def test_local_identity_is_impossible_on_a_public_deploy(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    monkeypatch.setattr(config, "PUBLIC_DEPLOY", True); monkeypatch.setattr(config, "GITHUB_CLIENT_ID", ""); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "")
    class Req: cookies = {}
    with pytest.raises(HTTPException) as e:
        asyncio.run(auth.require_user(Req()))
    assert e.value.status_code == 503


def test_local_development_is_unaffected(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DEPLOY", False)
    assert config.deploy_missing() == []


# ------------------------------------------------------------------ stateless sessions
def user(**kw):
    return auth.User(**{"login": "alice", "token": "gho_SECRETSECRETSECRET", "avatar": "https://a/x.png", "name": "Alice", "gh_login": "alice", "url": "https://github.com/alice", **kw})


def test_cookie_roundtrip_and_confidentiality(monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", KEY)
    u = user(); c = auth.seal(u); back = auth.unseal(c)
    assert back.login == "alice" and back.token == u.token and back.name == "Alice" and back.created == u.created
    assert "gho_SECRET" not in c and "alice" not in c                       # encrypted, not merely encoded
    import base64
    assert b"gho_SECRET" not in base64.urlsafe_b64decode(c + "=" * (-len(c) % 4))
    assert len(auth.seal(user(name="N" * 100, url="https://github.com/" + "u" * 100, avatar="https://a/" + "p" * 200))) < 3500   # fits in a cookie


def test_tampered_foreign_and_expired_cookies_are_rejected(monkeypatch):
    monkeypatch.setattr(config, "SECRET_KEY", KEY)
    c = auth.seal(user())
    assert auth.unseal(c[:-3] + ("AAA" if not c.endswith("AAA") else "BBB")) is None
    assert auth.unseal("not a cookie") is None and auth.unseal("") is None
    monkeypatch.setattr(config, "SECRET_KEY", "z" * 40)
    assert auth.unseal(c) is None                                           # signed with another key
    monkeypatch.setattr(config, "SECRET_KEY", KEY)
    import cryptography.fernet as f
    real = time.time
    monkeypatch.setattr(f.time, "time", lambda: real() + auth.SESSION_DAYS * 86400 + 60)
    assert auth.unseal(c) is None                                           # expired


def test_sessions_survive_a_cold_instance(monkeypatch, sqlite_db):
    """A new serverless instance has an empty memory. The cookie must still work."""
    monkeypatch.setattr(config, "SECRET_KEY", KEY); monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "id"); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "s")
    cookie = auth.seal(user())
    auth.SESSIONS.clear(); auth._epoch_cache.clear(); llm.ledger.sessions.clear()
    r = TestClient(app).get("/api/profile", cookies={"oss_session": cookie})
    assert r.status_code == 200 and r.json()["identity"]["login"] == "alice"
    assert TestClient(app).get("/api/profile").status_code == 401


def test_logout_really_revokes_the_cookie_everywhere(monkeypatch, sqlite_db):
    monkeypatch.setattr(config, "SECRET_KEY", KEY); monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "id"); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "s")
    monkeypatch.setattr(auth, "EPOCH_TTL", 0)
    old, other = auth.seal(user()), auth.seal(user(login="bob", gh_login="bob"))
    c = TestClient(app)
    assert c.get("/api/profile", cookies={"oss_session": old}).status_code == 200
    assert c.post("/auth/logout", cookies={"oss_session": old}).status_code == 200
    assert c.get("/api/profile", cookies={"oss_session": old}).status_code == 401      # a copied cookie is now useless
    assert c.get("/api/profile", cookies={"oss_session": other}).status_code == 200    # other students untouched
    time.sleep(0.01)
    assert c.get("/api/profile", cookies={"oss_session": auth.seal(user())}).status_code == 200   # signing in again works


def test_delete_my_data_revokes_and_wipes(monkeypatch, sqlite_db):
    monkeypatch.setattr(config, "SECRET_KEY", KEY); monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "id"); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "s")
    monkeypatch.setattr(auth, "EPOCH_TTL", 0)
    cookie = auth.seal(user()); c = TestClient(app)
    c.put("/api/profile", json={"answers": {"skill": "beginner"}}, cookies={"oss_session": cookie})
    usage_row = usage.add("alice", 0.1, 1, 1)
    assert c.delete("/api/profile", cookies={"oss_session": cookie}).status_code == 200
    assert c.get("/api/profile", cookies={"oss_session": cookie}).status_code == 401
    assert profiles.get("alice")["answers"] == {} and usage.summary("alice")["cost_usd"] == 0


def test_epoch_cache_bounds_revocation_delay(monkeypatch, sqlite_db):
    monkeypatch.setattr(auth, "EPOCH_TTL", 10)
    assert auth.epoch("zed") == 0.0
    with db.connect() as con:
        con.execute("INSERT INTO auth_epoch(uid, epoch) VALUES (?,?)", ("zed", 123.0))
    assert auth.epoch("zed") == 0.0                      # cached for up to EPOCH_TTL seconds
    auth._epoch_cache.clear()
    assert auth.epoch("zed") == 123.0


# ------------------------------------------------------------------ budgets that persist
class FakeClient:
    def __init__(self): self.calls = 0; self.messages = type("M", (), {"create": self._c})()
    def _c(self, **kw):
        from types import SimpleNamespace as N
        self.calls += 1
        return N(content=[N(type="text", text="ok")], stop_reason="end_turn", usage=N(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0))


def test_budget_is_enforced_from_the_database_across_instances(monkeypatch, sqlite_db):
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite-sentinel")   # truthy: switches the ledger to database mode
    monkeypatch.setattr(db, "connect", lambda: _sqlite_conn(sqlite_db))
    monkeypatch.setattr(llm, "CACHE_DIR", sqlite_db); monkeypatch.setattr(config, "SESSION_BUDGET_USD", 0.01)
    fc = FakeClient(); monkeypatch.setattr(llm, "_client", fc)
    ask = lambda m: llm.ask(tier="cheap", system="s", messages=[{"role": "user", "content": m}], max_tokens=50, session_id="alice", use_cache=False)
    ask("one")
    assert usage.today("alice") > 0
    llm.ledger.sessions.clear(); llm.ledger.total = llm.Usage()       # a different serverless instance: empty memory
    with pytest.raises(llm.BudgetExceeded):
        for i in range(30):
            ask(f"again {i}")
    assert fc.calls < 30 and "Daily budget" in str(pytest.raises(llm.BudgetExceeded, ask, "x").value)
    assert llm.session_usage("alice")["cost_usd"] > 0 and llm.session_usage("bob")["cost_usd"] == 0   # per student
    usage.delete("alice"); assert usage.today("alice") == 0


def _sqlite_conn(path):
    import sqlite3
    raw = sqlite3.connect(path / "d.db", timeout=15); raw.row_factory = sqlite3.Row
    for stmt in db.schema_sql(False): raw.execute(stmt)
    return db.Conn(raw, False)


# ------------------------------------------------------------------ catalogue ships with the deploy
def test_snapshot_is_used_when_no_runtime_file_exists(monkeypatch, tmp_path):
    snap = tmp_path / "snap.json"; snap.write_text(json.dumps({"generated_at": "2026-10-01T00:00:00+00:00", "counts": {}, "errors": {}, "entries": [{"name": "X"}]}))
    monkeypatch.setattr(catalogue, "FILE", tmp_path / "missing.json"); monkeypatch.setattr(catalogue, "SNAPSHOT", snap); catalogue._cached.clear()
    assert catalogue.load()["entries"][0]["name"] == "X"
    rt = tmp_path / "rt.json"; rt.write_text(json.dumps({"generated_at": "2026-10-02T00:00:00+00:00", "counts": {}, "errors": {}, "entries": [{"name": "Y"}]}))
    monkeypatch.setattr(catalogue, "FILE", rt); catalogue._cached.clear()
    assert catalogue.load()["entries"][0]["name"] == "Y"                   # a fresher runtime copy wins locally
    catalogue._cached.clear()


def test_public_deploy_never_starts_a_background_refresh(monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DEPLOY", True)
    started = []
    monkeypatch.setattr(catalogue.threading, "Thread", lambda *a, **k: started.append(1))
    catalogue.maybe_refresh_in_background()
    assert started == []


@pytest.mark.skipif(not catalogue.SNAPSHOT.exists(), reason="snapshot not generated yet: run `python -m backend.catalogue refresh --snapshot` and commit mentor/catalogue_snapshot.json")
def test_the_committed_snapshot_is_valid_and_large():
    d = json.loads(catalogue.SNAPSHOT.read_text())
    assert len(d["entries"]) >= 600 and d["generated_at"]
    for e in d["entries"][:50]:
        assert e["languages"] is not None and e["domains"] and e["rated"] == "auto" and e["github"]


def test_nothing_in_the_deploy_path_needs_a_writable_project_dir():
    """On Vercel only /tmp is writable. config.DATA must point there."""
    import importlib, os
    old = {k: os.environ.get(k) for k in ("VERCEL", "DATA_DIR")}
    try:
        os.environ["VERCEL"] = "1"; os.environ.pop("DATA_DIR", None)
        importlib.reload(config)
        assert str(config.DATA) == "/tmp/oss-mentor" and config.ON_VERCEL and config.PUBLIC_DEPLOY
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        importlib.reload(config)
