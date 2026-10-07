"""The whole GitHub sign-in flow against a FAKE GitHub: authorize redirect, callback, session, sign-out, and every failure path."""
import time
import urllib.parse as up

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import auth, config, db
from backend.app import app

BASE = "https://oss-mentor.example"
TOKEN = "gho_FAKE_ACCESS_TOKEN_1234567890"


class R:
    def __init__(self, data, code=200): self._d, self.status_code = data, code
    def json(self):
        if isinstance(self._d, Exception): raise self._d
        return self._d


@pytest.fixture
def gh(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "Iv1.fakeclientid"); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setattr(config, "BASE_URL", BASE); monkeypatch.setattr(config, "SECRET_KEY", "k" * 40); monkeypatch.setattr(config, "DATABASE_URL", "")
    monkeypatch.setattr(db, "PATH", tmp_path / "o.db"); db._ready.clear(); auth._epoch_cache.clear(); auth.SESSIONS.clear(); monkeypatch.setattr(auth, "EPOCH_TTL", 0)
    seen = {"token_requests": []}
    state = {"token": R({"access_token": TOKEN, "token_type": "bearer", "scope": "public_repo,read:user"}),
             "user": R({"login": "octocat", "name": "The Octocat", "avatar_url": "https://a/o.png", "html_url": "https://github.com/octocat"})}
    def post(url, **kw):
        seen["token_requests"].append((url, kw))
        if isinstance(state["token"], Exception): raise state["token"]
        return state["token"]
    def get(url, **kw):
        assert url == "https://api.github.com/user" and kw["headers"]["Authorization"] == f"Bearer {TOKEN}"
        if isinstance(state["user"], Exception): raise state["user"]
        return state["user"]
    monkeypatch.setattr(auth.httpx, "post", post); monkeypatch.setattr(auth.httpx, "get", get)
    c = TestClient(app, base_url=BASE, follow_redirects=False)
    return c, state, seen


def start(c):
    r = c.get("/auth/login")
    q = up.parse_qs(up.urlparse(r.headers["location"]).query)
    return r, q


def test_authorize_redirect_is_correct_and_safe(gh):
    c, _, _ = gh
    r, q = start(c)
    loc = r.headers["location"]
    assert r.status_code in (302, 307) and loc.startswith("https://github.com/login/oauth/authorize?")
    assert q["client_id"] == ["Iv1.fakeclientid"] and q["redirect_uri"] == [f"{BASE}/auth/callback"]
    assert set(q["scope"][0].split()) == {"public_repo", "read:user"}                 # least privilege: public repos + read profile
    assert "fake-client-secret" not in loc                                              # the secret never goes through the browser
    ck = r.headers["set-cookie"].lower()
    assert q["state"][0] in r.headers["set-cookie"] and "httponly" in ck and "samesite=lax" in ck and "secure" in ck


def full_login(c):
    _, q = start(c)
    r = c.get(f"/auth/callback?code=abc123&state={q['state'][0]}")
    return r


def test_full_sign_in_flow(gh):
    c, _, seen = gh
    r = full_login(c)
    assert r.status_code in (302, 307) and r.headers["location"] == "/"
    cookies = r.headers.get_list("set-cookie")
    sess = next(x for x in cookies if x.startswith("oss_session="))
    assert "httponly" in sess.lower() and "samesite=lax" in sess.lower() and "secure" in sess.lower() and "max-age=604800" in sess.lower()
    assert TOKEN not in sess and "octocat" not in sess                                  # the cookie is encrypted, not merely encoded
    url, kw = seen["token_requests"][0]                                                 # the code exchange used the secret server-side, with the right redirect_uri
    assert url == "https://github.com/login/oauth/access_token" and kw["data"]["client_secret"] == "fake-client-secret" and kw["data"]["code"] == "abc123"
    assert kw["data"]["redirect_uri"] == f"{BASE}/auth/callback"
    me = c.get("/api/me").json()                                                        # the browser keeps the cookie; now we are signed in
    assert me["login"] == "octocat" and me["name"] == "The Octocat" and me["mode"] == "github" and TOKEN not in str(me)
    assert c.get("/api/profile").status_code == 200


def test_user_can_cancel_on_github(gh):
    c, _, _ = gh
    _, q = start(c)
    r = c.get(f"/auth/callback?error=access_denied&state={q['state'][0]}")
    assert r.status_code in (302, 307) and r.headers["location"] == "/?login=cancelled"
    assert not any(x.startswith("oss_session=") and "max-age=604800" in x.lower() for x in r.headers.get_list("set-cookie"))
    assert c.get("/api/profile").status_code == 401


@pytest.mark.parametrize("path", ["/auth/callback", "/auth/callback?code=x", "/auth/callback?state=x", "/auth/callback?code=x&state=forged"])
def test_callback_rejects_forged_or_missing_state(gh, path):
    c, _, seen = gh
    start(c)
    assert c.get(path).status_code == 400 and seen["token_requests"] == []             # CSRF: GitHub is never even called


def test_callback_without_the_state_cookie_is_rejected(gh):
    c, _, _ = gh
    _, q = start(c); c.cookies.clear()
    assert c.get(f"/auth/callback?code=x&state={q['state'][0]}").status_code == 400


def test_github_refuses_the_code(gh):
    c, state, _ = gh
    state["token"] = R({"error": "bad_verification_code", "error_description": "The code passed is incorrect or expired."})
    r = full_login(c)
    assert r.status_code == 400 and "incorrect or expired" in r.json()["detail"]


@pytest.mark.parametrize("failure", [httpx.ConnectError("down"), httpx.ReadTimeout("slow"), ValueError("not json")])
def test_github_unreachable_gives_a_clean_502_not_a_crash(gh, failure):
    c, state, _ = gh
    state["token"] = failure
    assert full_login(c).status_code == 502


def test_profile_fetch_failures(gh):
    c, state, _ = gh
    state["user"] = R({"message": "Bad credentials"}, 401)
    assert full_login(c).status_code == 502
    state["user"] = R({"message": "oops"}, 200)                                         # 200 but no "login"
    assert full_login(c).status_code == 502
    state["user"] = httpx.ConnectError("down")
    assert full_login(c).status_code == 502
    assert c.get("/api/profile").status_code == 401                                      # none of the failures left a session behind


def test_sign_out_then_sign_in_again(gh):
    c, _, _ = gh
    full_login(c); assert c.get("/api/profile").status_code == 200
    old = c.cookies.get("oss_session")
    assert c.post("/auth/logout").status_code == 200 and c.get("/api/profile").status_code == 401
    c.cookies.set("oss_session", old); assert c.get("/api/profile").status_code == 401   # the old cookie is dead everywhere
    time.sleep(0.01); c.cookies.clear()
    full_login(c); assert c.get("/api/profile").status_code == 200                       # a fresh sign-in works


def test_works_without_a_secret_key_too_using_server_side_sessions(gh, monkeypatch):
    c, _, _ = gh
    monkeypatch.setattr(config, "SECRET_KEY", "")
    full_login(c)
    assert len(auth.SESSIONS) == 1 and c.get("/api/profile").status_code == 200


def test_login_requires_oauth_to_be_configured(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", ""); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "")
    monkeypatch.setattr(config, "PUBLIC_DEPLOY", False)
    assert TestClient(app, follow_redirects=False).get("/auth/login").status_code == 404
