"""GitHub OAuth login. Each student's token stays on the server and is used only for their own requests.

Hosted mode  : GITHUB_CLIENT_ID + GITHUB_CLIENT_SECRET set -> sign-in required, per-student token, budget and data.
Local mode   : no client id -> one user on this machine. Identity comes from the local `gh` login so the profile page shows who you
               really are; the storage key stays "local".
Sessions live in memory (a restart signs everyone out) and expire server-side after SESSION_DAYS.
"""
import secrets
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from . import config

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


def _session(request: Request) -> User | None:
    sid = request.cookies.get(COOKIE, "")
    u = SESSIONS.get(sid)
    if u and time.time() - u.created > SESSION_DAYS * 86400:
        SESSIONS.pop(sid, None)  # server-side expiry: a stolen or stale cookie stops working
        return None
    return u


async def require_user(request: Request) -> User:
    """Dependency: resolves the signed-in student and binds their token for this request."""
    if not hosted():
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
def callback(request: Request, code: str = "", state: str = ""):
    if not code or not state or not secrets.compare_digest(state, request.cookies.get(STATE_COOKIE, "")):
        raise HTTPException(400, "Login state mismatch. Start again.")
    tok = httpx.post("https://github.com/login/oauth/access_token",
                     data={"client_id": config.GITHUB_CLIENT_ID, "client_secret": config.GITHUB_CLIENT_SECRET,
                           "code": code, "redirect_uri": f"{config.BASE_URL}/auth/callback"},
                     headers={"Accept": "application/json"}, timeout=20).json().get("access_token")
    if not tok:
        raise HTTPException(400, "GitHub did not return a token.")
    me = httpx.get("https://api.github.com/user", headers={"Authorization": f"Bearer {tok}"}, timeout=20).json()
    if len(SESSIONS) >= MAX_SESSIONS:  # drop the oldest rather than grow without bound
        for k in sorted(SESSIONS, key=lambda k: SESSIONS[k].created)[:100]:
            SESSIONS.pop(k, None)
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = User(login=me["login"], token=tok, avatar=me.get("avatar_url", ""), name=me.get("name") or "", gh_login=me["login"], url=me.get("html_url", ""))
    r = RedirectResponse("/")
    r.set_cookie(COOKIE, sid, httponly=True, samesite="lax", secure=_secure(request), max_age=SESSION_DAYS * 86400)
    r.delete_cookie(STATE_COOKIE)
    return r


@router.post("/auth/logout")
def logout(request: Request):
    SESSIONS.pop(request.cookies.get(COOKIE, ""), None)
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r


@router.get("/api/me")
def me(request: Request):
    return public(_local_identity() if not hosted() else _session(request))
