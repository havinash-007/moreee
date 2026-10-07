"""GitHub OAuth login. Each student's token stays on the server and is used only for their own requests.

Hosted mode  : GITHUB_CLIENT_ID + GITHUB_CLIENT_SECRET set -> login required, per-student token and budget.
Local mode   : no client id -> single user, token from GITHUB_TOKEN or the local `gh` login.
"""
import secrets
from contextvars import ContextVar
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from . import config

router = APIRouter()
COOKIE = "oss_session"
STATE_COOKIE = "oss_oauth_state"
SCOPE = "public_repo read:user"  # public_repo only so the student can reply on their own public PRs


@dataclass
class User:
    login: str
    token: str
    avatar: str = ""


SESSIONS: dict[str, User] = {}  # in memory: restart logs everyone out (documented limit)
current_token: ContextVar[str] = ContextVar("current_token", default="")
current_login: ContextVar[str] = ContextVar("current_login", default="local")


def hosted() -> bool:
    return bool(config.GITHUB_CLIENT_ID and config.GITHUB_CLIENT_SECRET)


async def require_user(request: Request) -> User:
    """Dependency: resolves the logged-in student and binds their token for this request."""
    if not hosted():
        u = User(login="local", token=config.GITHUB_TOKEN)
    else:
        u = SESSIONS.get(request.cookies.get(COOKIE, ""))
        if not u:
            raise HTTPException(401, "Connect your GitHub account first.")
    current_token.set(u.token)
    current_login.set(u.login)
    return u


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
    if not code or not state or state != request.cookies.get(STATE_COOKIE):
        raise HTTPException(400, "Login state mismatch. Start again.")
    tok = httpx.post("https://github.com/login/oauth/access_token",
                     data={"client_id": config.GITHUB_CLIENT_ID, "client_secret": config.GITHUB_CLIENT_SECRET,
                           "code": code, "redirect_uri": f"{config.BASE_URL}/auth/callback"},
                     headers={"Accept": "application/json"}, timeout=20).json().get("access_token")
    if not tok:
        raise HTTPException(400, "GitHub did not return a token.")
    me = httpx.get("https://api.github.com/user", headers={"Authorization": f"Bearer {tok}"}, timeout=20).json()
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = User(login=me["login"], token=tok, avatar=me.get("avatar_url", ""))
    r = RedirectResponse("/")
    r.set_cookie(COOKIE, sid, httponly=True, samesite="lax", secure=_secure(request), max_age=60 * 60 * 24 * 7)
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
    if not hosted():
        return {"hosted": False, "login": "local"}
    u = SESSIONS.get(request.cookies.get(COOKIE, ""))
    return {"hosted": True, "login": u.login if u else None, "avatar": u.avatar if u else ""}
