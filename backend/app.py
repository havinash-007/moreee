"""FastAPI server: JSON API for the agents plus the static UI. Run: uvicorn backend.app:app"""
import os

import anthropic
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agents, auth, config, llm, matcher, replier

app = FastAPI(title="oss-mentor")
app.include_router(auth.router)


@app.middleware("http")
async def same_origin_posts(request: Request, call_next):
    """CSRF guard for cookie auth: state-changing requests must come from our own origin."""
    if request.method == "POST" and auth.hosted():
        origin = request.headers.get("origin", "")
        if origin and origin.rstrip("/") != config.BASE_URL:
            return JSONResponse({"error": "Cross-origin request blocked."}, status_code=403)
    return await call_next(request)

QUESTIONS = [
    {"id": "mode", "q": "How do you want to work?", "multi": False, "options": [
        ["learn", "Learn: I write the code, you coach me"],
        ["semi", "Semi-auto: I vibe code with AI, you quiz me"],
        ["full", "Full-auto: agents do it, I supervise"]]},
    {"id": "languages", "q": "Which languages can you read comfortably?", "multi": True, "options": [
        [x, x] for x in ["Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "C", "C++", "Ruby", "PHP", "Kotlin", "Swift", "Dart"]]},
    {"id": "skill", "q": "How strong are you in your best language?", "multi": False, "options": [
        ["beginner", "Beginner (courses only)"], ["intermediate", "Intermediate (built projects)"], ["advanced", "Advanced"]]},
    {"id": "interests", "q": "What are you most curious about?", "multi": True, "options": [
        ["web", "Web apps"], ["ai-ml-data", "AI / ML / data"], ["cloud-devops", "Cloud / DevOps"],
        ["security", "Security"], ["mobile", "Mobile"], ["devtools", "Developer tools"], ["education", "Docs / education"],
        ["social", "Social good / open science"], ["creative", "Games / creative coding"]]},
    {"id": "goal", "q": "What is your main goal?", "multi": False, "options": [
        ["hackathon", "A hackathon"], ["job", "Internship / job"], ["gsoc", "Google Summer of Code"], ["learn", "Learn and build a portfolio"]]},
    {"id": "time", "q": "How much time do you have?", "multi": False, "options": [
        ["lt5", "Under 5 hours a week"], ["5to10", "5 to 10 hours a week"], ["gt10", "10+ hours a week"], ["event", "A hackathon weekend"]]},
    {"id": "git_level", "q": "How comfortable are you with Git and GitHub?", "multi": False, "options": [
        ["never", "Never used it"], ["commit", "Commit and push only"], ["pr", "Branches and PRs"], ["rebase", "Fork and rebase"]]},
    {"id": "contrib_type", "q": "What first contribution do you want?", "multi": False, "options": [
        ["bug", "Bug fix"], ["docs", "Docs"], ["tests", "Tests"], ["feature", "Small feature"], ["any", "Pick for me"]]},
    {"id": "machine", "q": "What can your machine run?", "multi": False, "options": [
        ["low", "Low-spec laptop"], ["normal", "Normal laptop"], ["docker", "Docker and big builds"]]},
    {"id": "legal", "q": "OK with DCO/CLA sign-offs and disclosing AI help when asked?", "multi": False, "options": [
        ["both", "Yes to both"], ["dco", "DCO only"], ["unsure", "Not sure, explain it"]]},
]


class Profile(BaseModel):
    mode: str = "learn"
    languages: list[str] = []
    skill: str = "beginner"
    interests: list[str] = []
    goal: str = "learn"
    time: str = "lt5"
    git_level: str = "never"
    contrib_type: str = "any"
    machine: str = "normal"
    legal: str = "both"


class ScoutReq(BaseModel):
    org: str
    repo: str | None = None
    profile: Profile
    session: str = "default"


class TourReq(BaseModel):
    repo: str
    issue_title: str
    level: str = "beginner"
    session: str = "default"


class CoachReq(BaseModel):
    mode: str
    context: str = ""
    history: list[dict]
    session: str = "default"


class DraftReq(BaseModel):
    pr_url: str
    session: str = "default"


class SendReq(BaseModel):
    pr_url: str
    items: list[dict]
    disclose: bool = True


@app.exception_handler(llm.BudgetExceeded)
async def _budget(_, e):
    return JSONResponse({"error": str(e), "kind": "budget"}, status_code=402)


@app.exception_handler(anthropic.AuthenticationError)
async def _auth(_, e):
    return JSONResponse({"error": "Anthropic API key is missing or invalid. Set ANTHROPIC_API_KEY in .env.", "kind": "auth"}, status_code=503)


@app.exception_handler(anthropic.APIError)
async def _api(_, e):
    return JSONResponse({"error": f"Claude API error: {getattr(e, 'message', e)}", "kind": "claude"}, status_code=502)


@app.exception_handler(httpx.HTTPError)
async def _gh(_, e):
    return JSONResponse({"error": f"GitHub request failed: {e}", "kind": "github"}, status_code=502)


@app.exception_handler(PermissionError)
async def _perm(_, e):
    return JSONResponse({"error": str(e), "kind": "disabled"}, status_code=403)


@app.get("/api/health")
def health():
    return {"anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")), "github_token": bool(config.GITHUB_TOKEN) or auth.hosted(),
            "posting_enabled": config.AUTO_POST_REPLIES, "hosted": auth.hosted(), "models": {"cheap": config.MODEL_CHEAP, "smart": config.MODEL_SMART},
            "session_budget_usd": config.SESSION_BUDGET_USD}


@app.get("/api/orgs")
def orgs():
    """Public catalogue for the 3D galaxy (no secrets, no user data)."""
    return [{k: o[k] for k in ("name", "github", "languages", "domains", "beginner", "notes")} for o in matcher.catalogue()]


@app.get("/api/questions")
def questions():
    return QUESTIONS


@app.post("/api/match")
def match(p: Profile, user: auth.User = Depends(auth.require_user)):
    top, others = matcher.rank_all(p.model_dump())
    return {"ranking": top, "others": others, "catalogue_size": len(matcher.catalogue()), "cost_usd": 0.0}


@app.get("/api/discover")
def discover(languages: str = "", interests: str = "", user: auth.User = Depends(auth.require_user)):
    """Live GitHub search for repos with open good-first-issues that are not already in our catalogue."""
    from . import github
    known = {o["github"].lower() for o in matcher.catalogue()}
    langs = [x for x in languages.split(",") if x]
    ints = [x for x in interests.split(",") if x]
    return {"repos": github.discover(langs, ints, known), "cost_usd": 0.0}


@app.post("/api/scout")
def scout(r: ScoutReq, user: auth.User = Depends(auth.require_user)):
    return agents.scout(r.org, r.profile.model_dump(), user.login, r.repo)


@app.post("/api/tour")
def tour(r: TourReq, user: auth.User = Depends(auth.require_user)):
    return agents.tour(r.repo, r.issue_title, r.level, user.login)


@app.post("/api/coach")
def coach(r: CoachReq, user: auth.User = Depends(auth.require_user)):
    if r.mode not in ("learn", "semi"):
        raise HTTPException(400, "Coach chat is for learn and semi modes.")
    return agents.coach(r.mode, r.context, r.history, user.login)


@app.post("/api/replies/draft")
def replies_draft(r: DraftReq, user: auth.User = Depends(auth.require_user)):
    try:
        return replier.draft(r.pr_url, user.login)
    except ValueError:
        raise HTTPException(400, "That does not look like a pull request URL.")


@app.post("/api/replies/send")
def replies_send(r: SendReq, user: auth.User = Depends(auth.require_user)):
    return replier.send(r.pr_url, r.items, r.disclose, user.login)


@app.get("/api/usage")
def usage(user: auth.User = Depends(auth.require_user)):
    return {"session": llm.ledger.session(user.login).as_dict(), "total": llm.ledger.total.as_dict(),
            "session_budget_usd": config.SESSION_BUDGET_USD}


@app.get("/")
def index():
    return FileResponse(config.ROOT / "frontend" / "v2" / "index.html")


@app.get("/classic")
def classic():
    return FileResponse(config.ROOT / "frontend" / "index.html")


app.mount("/static", StaticFiles(directory=config.ROOT / "frontend"), name="static")
