import time

import httpx
import pytest

from backend import auth, config, db, github, jobs, llm, profiles
from backend.app import QUESTIONS, app


@pytest.fixture
def pdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "p.db"); db._ready.clear()
    monkeypatch.setattr(github, "policy_scan", lambda o, r: {"files": [], "ai_flags": [], "legal": []})
    monkeypatch.setattr(github, "verify_issue", lambda *a, **k: {"ok": True, "reason": "", "checked_at": "t", "linked_prs": []})
    return tmp_path


@pytest.fixture
def client(pdb, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "id"); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "s"); monkeypatch.setattr(config, "BASE_URL", "http://testserver")
    auth.SESSIONS.clear()
    auth.SESSIONS["A"] = auth.User("alice", "SECRET-TOKEN-A", avatar="http://a/av.png", name="Alice A", gh_login="alice", url="https://github.com/alice")
    auth.SESSIONS["B"] = auth.User("bob", "SECRET-TOKEN-B", gh_login="bob")
    llm.ledger.sessions.clear()
    c = TestClient(app)
    c.cookies.clear()
    return c


A, B = {"oss_session": "A"}, {"oss_session": "B"}
GOOD = {"languages": ["Python", "Go"], "interests": ["web"], "skill": "beginner", "goal": "hackathon", "mode": "learn", "machine": "low"}


# ------------------------------------------------------------------ validation
def test_validate_accepts_real_answers_and_dedupes():
    out = profiles.validate({**GOOD, "languages": ["Python", "Python", "Go"]}, QUESTIONS)
    assert out["languages"] == ["Python", "Go"] and out["mode"] == "learn"


@pytest.mark.parametrize("bad", [
    {"nonsense": "x"}, {"skill": "wizard"}, {"languages": "Python"}, {"languages": ["Cobol"]}, {"mode": ["learn"]},
    {"languages": ["Python"] * 20}, {"interests": [1, 2]}, {"goal": None},
])
def test_validate_rejects_unknown_fields_and_values(bad):
    with pytest.raises(profiles.ProfileError):
        profiles.validate(bad, QUESTIONS)


def test_validate_rejects_non_objects():
    with pytest.raises(profiles.ProfileError):
        profiles.validate(["x"], QUESTIONS)


@pytest.mark.parametrize("bad", [{"theme": "dark"}, {"signoff_default": "yes"}, ["x"]])
def test_settings_validation(bad):
    with pytest.raises(profiles.ProfileError):
        profiles.validate_settings(bad)


# ------------------------------------------------------------------ store
def test_roundtrip_merge_and_isolation(pdb):
    assert profiles.get("alice")["answers"] == {} and profiles.get("alice")["settings"] == {"signoff_default": False}
    profiles.save("alice", GOOD, {"signoff_default": True}, QUESTIONS)
    profiles.save("alice", {**GOOD, "skill": "advanced"}, None, QUESTIONS)          # settings untouched when omitted
    a = profiles.get("alice")
    assert a["answers"]["skill"] == "advanced" and a["settings"]["signoff_default"] is True and a["updated"]
    profiles.save("alice", None, {"signoff_default": False}, QUESTIONS)              # answers untouched when omitted
    assert profiles.get("alice")["answers"]["skill"] == "advanced"
    assert profiles.get("bob")["answers"] == {}


def test_invalid_save_does_not_overwrite_good_data(pdb):
    profiles.save("alice", GOOD, None, QUESTIONS)
    with pytest.raises(profiles.ProfileError):
        profiles.save("alice", {"skill": "wizard"}, None, QUESTIONS)
    assert profiles.get("alice")["answers"]["skill"] == "beginner"


# ------------------------------------------------------------------ HTTP + auth
def test_profile_requires_sign_in_when_hosted(client):
    for m, path in [("get", "/api/profile"), ("put", "/api/profile"), ("get", "/api/profile/export"), ("delete", "/api/profile")]:
        assert getattr(client, m)(path).status_code == 401, path


def test_get_put_and_isolation_over_http(client):
    r = client.get("/api/profile", cookies=A).json()
    assert r["identity"]["login"] == "alice" and r["identity"]["name"] == "Alice A" and r["auth"]["mode"] == "github" and r["answers"] == {}
    assert client.put("/api/profile", json={"answers": GOOD, "settings": {"signoff_default": True}}, cookies=A).json()["answers"]["goal"] == "hackathon"
    assert client.get("/api/profile", cookies=A).json()["settings"]["signoff_default"] is True
    assert client.get("/api/profile", cookies=B).json()["answers"] == {}                       # bob sees none of alice's data
    assert client.put("/api/profile", json={"answers": {"skill": "wizard"}}, cookies=A).status_code == 422
    assert client.put("/api/profile", json={"answers": {"hack": "x"}}, cookies=A).status_code == 422


def _keys(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _keys(v)
    elif isinstance(x, list):
        for v in x:
            yield from _keys(v)


def test_identity_payload_never_contains_the_token(client):
    for path in ("/api/me", "/api/profile"):
        r = client.get(path, cookies=A)
        assert "SECRET-TOKEN-A" not in r.text and "SECRET-TOKEN-B" not in r.text
        assert not {"token", "access_token", "token_hash", "claim_token"} & set(_keys(r.json())), path


def test_export_contains_my_data_and_no_secrets(client):
    client.put("/api/profile", json={"answers": GOOD}, cookies=A)
    j = jobs.create("alice", "acme/widgets", 7, "T", True, False)
    r = client.get("/api/profile/export", cookies=A)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    d = r.json()
    assert d["profile"]["answers"]["goal"] == "hackathon" and d["jobs"][0]["id"] == j["id"] and d["identity"]["login"] == "alice"
    blob = r.text
    assert "SECRET-TOKEN-A" not in blob and j["token"] not in blob and "token_hash" not in blob
    assert "bob" not in blob


def test_delete_removes_everything_and_signs_out(client):
    client.put("/api/profile", json={"answers": GOOD}, cookies=A)
    ja = jobs.create("alice", "acme/widgets", 7, "T", True, False)
    jb = jobs.create("bob", "acme/gadgets", 3, "T", True, False)
    llm.ledger.session("alice").cost_usd = 0.3
    r = client.delete("/api/profile", cookies=A)
    assert r.status_code == 200 and r.json()["deleted_jobs"] == 1
    assert profiles.get("alice")["answers"] == {} and jobs.list_for("alice") == []
    assert "alice" not in llm.ledger.sessions
    assert "A" not in auth.SESSIONS and client.get("/api/profile", cookies=A).status_code == 401   # signed out
    assert jobs.get("bob", jb["id"])["status"] == "ready"                                          # bob untouched
    with pytest.raises(jobs.JobError) as e:                                                         # a runner for the deleted job is rejected
        jobs.runner_event(ja["id"], ja["token"], "x", "late")
    assert e.value.status == 403


def test_sessions_expire_server_side(client, monkeypatch):
    assert client.get("/api/profile", cookies=A).status_code == 200
    real = time.time
    monkeypatch.setattr(auth.time, "time", lambda: real() + auth.SESSION_DAYS * 86400 + 5)
    assert client.get("/api/profile", cookies=A).status_code == 401
    assert "A" not in auth.SESSIONS


def test_logout_invalidates_the_session(client):
    assert client.post("/auth/logout", cookies=A).status_code == 200
    assert client.get("/api/profile", cookies=A).status_code == 401
    assert client.get("/api/me", cookies=A).json()["login"] is None


def test_oauth_state_mismatch_is_rejected(client):
    assert client.get("/auth/callback?code=x&state=evil").status_code == 400
    client.cookies.set("oss_oauth_state", "right")
    assert client.get("/auth/callback?code=x&state=wrong").status_code == 400


# ------------------------------------------------------------------ local mode identity
def test_local_mode_shows_the_real_github_identity(pdb, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", ""); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", ""); monkeypatch.setattr(config, "GITHUB_TOKEN", "local-tok")
    auth._local.clear()
    class R:
        status_code = 200
        def json(self): return {"login": "havinash-007", "name": "Havinash", "avatar_url": "http://av/x.png", "html_url": "https://github.com/havinash-007"}
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: R())
    me = TestClient(app).get("/api/me").json()
    assert me["mode"] == "local" and me["login"] == "havinash-007" and me["name"] == "Havinash" and me["key"] == "local" and "local-tok" not in str(me)
    auth._local.clear()


def test_local_identity_failure_is_soft(pdb, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", ""); monkeypatch.setattr(config, "GITHUB_TOKEN", "t")
    auth._local.clear()
    def boom(*a, **k): raise httpx.ConnectError("offline")
    monkeypatch.setattr(auth.httpx, "get", boom)
    assert TestClient(app).get("/api/me").json()["login"] == "local"
    auth._local.clear()
