"""FastAPI server: JSON API for the agents plus the static UI. Run: uvicorn backend.app:app"""
import os

import anthropic
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agents, config, llm, matcher, replier

app = FastAPI(title="oss-mentor")

QUESTIONS = [
    {"id": "mode", "q": "How do you want to work?", "multi": False, "options": [
        ["learn", "Learn: I write the code, you coach me"],
        ["semi", "Semi-auto: I vibe code with AI, you quiz me"],
        ["full", "Full-auto: agents do it, I supervise"]]},
    {"id": "languages", "q": "Which languages can you read comfortably?", "multi": True, "options": [
        [x, x] for x in ["Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "C++"]]},
    {"id": "skill", "q": "How strong are you in your best language?", "multi": False, "options": [
        ["beginner", "Beginner (courses only)"], ["intermediate", "Intermediate (built projects)"], ["advanced", "Advanced"]]},
    {"id": "interests", "q": "What are you most curious about?", "multi": True, "options": [
        ["web", "Web apps"], ["ai-ml-data", "AI / ML / data"], ["cloud-devops", "Cloud / DevOps"],
        ["security", "Security"], ["mobile", "Mobile"], ["devtools", "Developer tools"], ["education", "Docs / education"]]},
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
    return {"anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")), "github_token": bool(config.GITHUB_TOKEN),
            "posting_enabled": config.AUTO_POST_REPLIES, "models": {"cheap": config.MODEL_CHEAP, "smart": config.MODEL_SMART},
            "session_budget_usd": config.SESSION_BUDGET_USD}


@app.get("/api/questions")
def questions():
    return QUESTIONS


@app.post("/api/match")
def match(p: Profile):
    return {"ranking": matcher.rank(p.model_dump(), top=3), "cost_usd": 0.0}


@app.post("/api/scout")
def scout(r: ScoutReq):
    return agents.scout(r.org, r.profile.model_dump(), r.session)


@app.post("/api/tour")
def tour(r: TourReq):
    return agents.tour(r.repo, r.issue_title, r.level, r.session)


@app.post("/api/coach")
def coach(r: CoachReq):
    if r.mode not in ("learn", "semi"):
        raise HTTPException(400, "Coach chat is for learn and semi modes.")
    return agents.coach(r.mode, r.context, r.history, r.session)


@app.post("/api/replies/draft")
def replies_draft(r: DraftReq):
    try:
        return replier.draft(r.pr_url, r.session)
    except ValueError:
        raise HTTPException(400, "That does not look like a pull request URL.")


@app.post("/api/replies/send")
def replies_send(r: SendReq):
    return replier.send(r.pr_url, r.items, r.disclose)


@app.get("/api/usage")
def usage(session: str = "default"):
    return {"session": llm.ledger.session(session).as_dict(), "total": llm.ledger.total.as_dict(),
            "session_budget_usd": config.SESSION_BUDGET_USD}


@app.get("/")
def index():
    return FileResponse(config.ROOT / "frontend" / "index.html")


app.mount("/static", StaticFiles(directory=config.ROOT / "frontend"), name="static")
