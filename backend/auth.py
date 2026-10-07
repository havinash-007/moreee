"""GitHub OAuth login. Each student's token stays on the server and is used only for their own requests.

Hosted mode  : GITHUB_CLIENT_ID + GITHUB_CLIENT_SECRET set -> sign-in required, per-student token, budget and data.
Local mode   : no client id -> one user on this machine. Identity comes from the local `gh` login so the profile page shows who you
               really are; the storage key stays "local".
Sessions live in memory (a restart signs everyone out) and expire server-side after SESSION_DAYS.
"""
import base64
import hashlib
import json
import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from . import config, db

router = APIRouter()
COOKIE = "oss_session"
STATE_COOKIE = "oss_oauth_state"
SCOPE = "public_repo read:user"  # public_repo only so the student can reply on their own public PRs
SESSION_DAYS = 7
MAX_SESSIONS = 5000


@dataclass
class User:
    login: str                 # storage key: the GitHub login in hosted mode, "local" in local mode
    token: str
    avatar: str = ""
    name: str = ""
    gh_login: str = ""         # the real GitHub login to display (equals login when hosted)
    url: str = ""
    created: float = field(default_factory=time.time)


SESSIONS: dict[str, User] = {}
current_token: ContextVar[str] = ContextVar("current_token", default="")
current_login: ContextVar[str] = ContextVar("current_login", default="local")
_local: dict = {}


def hosted() -> bool:
    return bool(config.GITHUB_CLIENT_ID and config.GITHUB_CLIENT_SECRET)


def _local_identity() -> User:
    """Who is running this on their own machine? Ask GitHub once per 10 minutes using the local token. Fails soft."""
    now = time.time()
    if _local.get("t", 0) > now - 600 and _local.get("tok") == config.GITHUB_TOKEN:
        return _local["u"]
    u = User(login="local", token=config.GITHUB_TOKEN)
    if config.GITHUB_TOKEN:
        try:
            r = httpx.get("https://api.github.com/user", headers={"Authorization": f"Bearer {config.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}, timeout=8)
            if r.status_code == 200:
                d = r.json()
                u = User(login="local", token=config.GITHUB_TOKEN, avatar=d.get("avatar_url", ""), name=d.get("name") or "", gh_login=d.get("login", ""), url=d.get("html_url", ""))
        except httpx.HTTPError:
            pass
    _local.update(t=now, tok=config.GITHUB_TOKEN, u=u)
    return u


# ---- stateless sessions (used whenever SECRET_KEY is set, which a serverless deployment requires) -------------------------
# The cookie itself is the session: an AES-encrypted, tamper-proof (Fernet) blob holding the student's identity and GitHub token.
# The browser cannot read or alter it, and any server instance can open it, so nothing has to be shared between instances.
# Sign-out and "delete my data" bump a per-student epoch in the database; cookies issued before it stop working everywhere.
_epoch_cache: dict[str, tuple[float, float]] = {}
EPOCH_TTL = 10  # seconds a server instance may cache a student's epoch (bounds how long a revoked cookie can still work elsewhere)


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(config.SECRET_KEY.encode()).digest()))


def seal(u: User) -> str:
    payload = {"login": u.login, "token": u.token, "avatar": u.avatar, "name": u.name, "gh": u.gh_login, "url": u.url, "iat": u.created}
    return _fernet().encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()


def unseal(value: str) -> User | None:
    from cryptography.fernet import InvalidToken
    try:
        d = json.loads(_fernet().decrypt(value.encode(), ttl=SESSION_DAYS * 86400))
        return User(login=d["login"], token=d["token"], avatar=d.get("avatar", ""), name=d.get("name", ""), gh_login=d.get("gh", ""), url=d.get("url", ""), created=float(d["iat"]))
    except (InvalidToken, ValueError, KeyError, TypeError):
        return None


def epoch(uid: str) -> float:
    now = time.time()
    hit = _epoch_cache.get(uid)
    if hit and now - hit[0] < EPOCH_TTL:
        return hit[1]
    with db.connect() as con:
        r = con.execute("SELECT epoch FROM auth_epoch WHERE uid=?", (uid,)).fetchone()
    e = float(r[0]) if r else 0.0
    _epoch_cache[uid] = (now, e)
    return e


def revoke(uid: str) -> None:
    """Invalidate every sign-in cookie issued to this student so far (all devices)."""
    now = time.time()
    with db.connect() as con:
        con.execute("INSERT INTO auth_epoch(uid, epoch) VALUES (?,?) ON CONFLICT(uid) DO UPDATE SET epoch=excluded.epoch", (uid, now))
    _epoch_cache[uid] = (now, now)


def _session(request: Request) -> User | None:
    val = request.cookies.get(COOKIE, "")
    if config.SECRET_KEY:
        u = unseal(val) if val else None
        if u and u.created <= epoch(u.login):
            return None  # signed out (or data deleted) after this cookie was issued
        return u
    u = SESSIONS.get(val)
    if u and time.time() - u.created > SESSION_DAYS * 86400:
        SESSIONS.pop(val, None)  # server-side expiry: a stolen or stale cookie stops working
        return None
    return u


async def require_user(request: Request) -> User:
    """Dependency: resolves the signed-in student and binds their token for this request."""
    if not hosted():
        if config.PUBLIC_DEPLOY:  # defence in depth: a public site must never fall back to the operator's own identity
            raise HTTPException(503, "This deployment is not configured for sign-in yet.")
        u = _local_identity()
    else:
        u = _session(request)
        if not u:
            raise HTTPException(401, "Connect your GitHub account first.")
    current_token.set(u.token)
    current_login.set(u.login)
    return u


def public(u: User | None) -> dict:
    """What the browser may know about the signed-in user. Never the token."""
    hosted_ = hosted()
    if not u:
        return {"hosted": hosted_, "login": None, "name": "", "avatar": "", "url": "", "mode": "github" if hosted_ else "local"}
    shown = u.gh_login or (u.login if u.login != "local" else "")
    return {"hosted": hosted_, "login": shown or "local", "name": u.name, "avatar": u.avatar, "url": u.url or (f"https://github.com/{shown}" if shown else ""),
            "mode": "github" if hosted_ else "local", "key": u.login}


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or config.BASE_URL.startswith("https")


@router.get("/auth/login")
def login(request: Request):
    if not hosted():
        raise HTTPException(404, "OAuth is not configured; running in local mode.")
    state = secrets.token_urlsafe(24)
    url = (f"https://github.com/login/oauth/authorize?client_id={config.GITHUB_CLIENT_ID}"
           f"&scope={SCOPE.replace(' ', '%20')}&state={state}&redirect_uri={config.BASE_URL}/auth/callback")
    r = RedirectResponse(url)
    r.set_cookie(STATE_COOKIE, state, httponly=True, samesite="lax", secure=_secure(request), max_age=600)
    return r


@router.get("/auth/callback")
def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    def back(flag: str = ""):
        r = RedirectResponse("/" + (f"?login={flag}" if flag else ""))
        r.delete_cookie(STATE_COOKIE)
        return r

    if error:  # the student pressed Cancel on GitHub's page: send them home, no error screen
        return back("cancelled")
    if not code or not state or not secrets.compare_digest(state, request.cookies.get(STATE_COOKIE, "")):
        raise HTTPException(400, "Login state mismatch. Start again.")
    try:
        reply = httpx.post("https://github.com/login/oauth/access_token",
                           data={"client_id": config.GITHUB_CLIENT_ID, "client_secret": config.GITHUB_CLIENT_SECRET,
                                 "code": code, "redirect_uri": f"{config.BASE_URL}/auth/callback"},
                           headers={"Accept": "application/json"}, timeout=20).json()
        tok = reply.get("access_token") if isinstance(reply, dict) else None
        if not tok:
            why = (reply.get("error_description") or reply.get("error") or "no token") if isinstance(reply, dict) else "no token"
            raise HTTPException(400, f"GitHub refused the login ({why}). Start again.")
        mr = httpx.get("https://api.github.com/user", headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}, timeout=20)
        me = mr.json()
        if mr.status_code != 200 or not isinstance(me, dict) or "login" not in me:
            raise HTTPException(502, "GitHub did not return your profile. Try again.")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Could not reach GitHub. Try again in a moment.")
    if len(SESSIONS) >= MAX_SESSIONS:  # drop the oldest rather than grow without bound
        for k in sorted(SESSIONS, key=lambda k: SESSIONS[k].created)[:100]:
            SESSIONS.pop(k, None)
    user = User(login=me["login"], token=tok, avatar=me.get("avatar_url", ""), name=me.get("name") or "", gh_login=me["login"], url=me.get("html_url", ""))
    if config.SECRET_KEY:
        sid = seal(user)  # stateless: the cookie carries the session
    else:
        sid = secrets.token_urlsafe(32)
        SESSIONS[sid] = user
    r = back()
    r.set_cookie(COOKIE, sid, httponly=True, samesite="lax", secure=_secure(request), max_age=SESSION_DAYS * 86400)
    return r


@router.post("/auth/logout")
def logout(request: Request):
    u = _session(request)
    if config.SECRET_KEY and u:
        revoke(u.login)  # real sign-out: this cookie (and any copy of it) stops working immediately
    SESSIONS.pop(request.cookies.get(COOKIE, ""), None)
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r


@router.get("/api/me")
def me(request: Request):
    return public(_local_identity() if not hosted() else _session(request))
