"""FastAPI server: JSON API for the agents plus the static UI. Run: uvicorn backend.app:app"""
import json
import os

import anthropic
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agents, auth, catalogue, config, jobs, llm, matcher, replier

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
    fallback_orgs: list[str] = []
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


@app.exception_handler(jobs.JobError)
async def _job(_, e):
    return JSONResponse({"error": str(e), "kind": "job"}, status_code=e.status)


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


@app.on_event("startup")
def _startup():
    if os.getenv("CATALOGUE_AUTO_REFRESH", "true").lower() == "true":
        catalogue.maybe_refresh_in_background()  # never blocks startup; no-op when the file is fresh


@app.get("/api/orgs")
def orgs():
    """Featured set for the 3D galaxy (curated + this year's GSoC organisations). The matcher scores the whole catalogue."""
    seen, out = set(), []
    this_year = __import__("datetime").datetime.now().year
    for o in matcher.catalogue():
        if not (o.get("rated") == "curated" or this_year in o.get("gsoc_years", [])):
            continue
        k = o["name"].lower()
        if k in seen:
            continue
        seen.add(k)
        out.append({k2: o.get(k2) for k2 in ("name", "github", "repo", "languages", "domains", "beginner", "notes")} |
                   {"sources": o.get("sources", []), "gsoc": bool(o.get("gsoc_years")), "lfx": bool(o.get("lfx"))})
        if len(out) >= 300:
            break
    return out


@app.get("/api/catalogue/status")
def catalogue_status():
    st = catalogue.status()
    st["size"] = len(matcher.catalogue())
    st["curated"] = len(matcher.curated())
    return st


@app.get("/api/catalogue/browse")
def catalogue_browse(q: str = "", source: str = "", language: str = "", domain: str = "", page: int = 1, size: int = 24):
    """Search and filter every organisation we know about. Facet counts reflect the current filters."""
    size = max(1, min(size, 60))
    ql = q.lower().strip()

    def match(o, skip=()):
        if ql and ql not in (o["name"] + " " + (o.get("notes") or "") + " " + (o.get("repo") or o["github"])).lower():
            return False
        if "source" not in skip and source and not (source in o.get("sources", []) or (source == "gsoc" and o.get("gsoc_years")) or (source == "lfx" and o.get("lfx")) or (source == "cncf" and o.get("cncf")) or (source == "apache" and o.get("apache"))):
            return False
        if "language" not in skip and language and language not in o["languages"]:
            return False
        if "domain" not in skip and domain and domain not in o["domains"]:
            return False
        return True

    allo = matcher.catalogue()
    hits = [o for o in allo if match(o)]
    hits.sort(key=lambda o: (o.get("rated") != "curated", -(o.get("gfi") or 0), -(o.get("stars") or 0)))
    start = (max(page, 1) - 1) * size

    def facet(vals, skip):
        c = {}
        for o in allo:
            if match(o, skip=(skip,)):
                for v in vals(o):
                    c[v] = c.get(v, 0) + 1
        return dict(sorted(c.items(), key=lambda kv: -kv[1])[:25])

    cols = ("name", "github", "repo", "languages", "domains", "notes", "sources", "gsoc_years", "lfx", "cncf", "apache", "stars", "gfi", "url", "ideas_url", "rated")
    return {"total": len(hits), "page": page, "size": size, "items": [{k: o.get(k) for k in cols} for o in hits[start:start + size]],
            "facets": {"language": facet(lambda o: o["languages"], "language"), "domain": facet(lambda o: o["domains"], "domain"),
                       "source": facet(lambda o: ([s for s in ("gsoc", "lfx", "cncf", "apache") if (o.get(s) or (s == "gsoc" and o.get("gsoc_years")))] + (["curated"] if o.get("rated") == "curated" else []) + (["beginner-list"] if "beginner-list" in o.get("sources", []) else [])), "source")}}


@app.post("/api/catalogue/refresh")
def catalogue_refresh(user: auth.User = Depends(auth.require_user)):
    admins = {a.strip().lower() for a in os.getenv("ADMIN_LOGINS", "").split(",") if a.strip()}
    if auth.hosted() and user.login.lower() not in admins:
        raise PermissionError("Only an operator can refresh the catalogue.")
    import threading
    if not catalogue.STATE["refreshing"]:
        threading.Thread(target=lambda: catalogue.refresh(True, log=lambda *_: None), daemon=True).start()
    return catalogue.status()


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
    return agents.scout(r.org, r.profile.model_dump(), user.login, r.repo, r.fallback_orgs)


@app.post("/api/scout/stream")
def scout_stream(r: ScoutReq, user: auth.User = Depends(auth.require_user)):
    """Newline-delimited JSON: progress steps as they happen, then one result (or one error) event."""
    def gen():
        try:
            for ev in agents.scout_stream(r.org, r.profile.model_dump(), user.login, r.repo, r.fallback_orgs):
                yield json.dumps(ev) + "\n"
        except llm.BudgetExceeded as e:
            yield json.dumps({"type": "error", "kind": "budget", "error": str(e)}) + "\n"
        except anthropic.AuthenticationError:
            yield json.dumps({"type": "error", "kind": "auth", "error": "auth"}) + "\n"
        except httpx.HTTPError as e:
            yield json.dumps({"type": "error", "kind": "github", "error": f"GitHub request failed: {e}"}) + "\n"
        except anthropic.APIError as e:
            yield json.dumps({"type": "error", "kind": "claude", "error": str(getattr(e, "message", e))}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


class VerifyReq(BaseModel):
    repo: str
    number: int


@app.post("/api/verify")
def verify(r: VerifyReq, user: auth.User = Depends(auth.require_user)):
    """Fresh, uncached check that an issue is still open, unassigned, unclaimed and has no open PR."""
    from . import github
    owner, repo = r.repo.split("/")
    return github.verify_issue(owner, repo, r.number)


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


# ------------------------------------------------------------------ Full-auto jobs (the worker runs on the student's machine)
class JobReq(BaseModel):
    repo: str
    number: int
    title: str = ""
    consent: bool = False
    signoff: bool = False


class ApproveReq(BaseModel):
    pr_title: str
    pr_body: str
    cla_confirmed: bool = False


@app.post("/api/jobs")
def jobs_create(r: JobReq, request: Request, user: auth.User = Depends(auth.require_user)):
    j = jobs.create(user.login, r.repo, r.number, r.title, r.consent, r.signoff)
    base = str(request.base_url).rstrip("/")
    j["command"] = f"cd ~/oss-mentor && .venv/bin/python -m backend.runner {j['id']} {j['token']} --server {base}"
    return j


@app.get("/api/jobs")
def jobs_list(user: auth.User = Depends(auth.require_user)):
    return jobs.list_for(user.login)


@app.get("/api/jobs/{job_id}")
def jobs_get(job_id: str, since: int = 0, user: auth.User = Depends(auth.require_user)):
    return jobs.get(user.login, job_id, since)


@app.post("/api/jobs/{job_id}/approve")
def jobs_approve(job_id: str, r: ApproveReq, user: auth.User = Depends(auth.require_user)):
    return jobs.approve(user.login, job_id, r.pr_title, r.pr_body, r.cla_confirmed)


@app.post("/api/jobs/{job_id}/cancel")
def jobs_cancel(job_id: str, user: auth.User = Depends(auth.require_user)):
    return jobs.cancel(user.login, job_id)


class RunnerEvent(BaseModel):
    stage: str = ""
    text: str


class RunnerDone(BaseModel):
    pr_url: str | None = None
    error: str | None = None


@app.get("/api/runner/{job_id}/spec")
def runner_spec(job_id: str, x_job_token: str = Header("")):
    return jobs.spec(job_id, x_job_token)


@app.post("/api/runner/{job_id}/event")
def runner_event(job_id: str, e: RunnerEvent, x_job_token: str = Header("")):
    jobs.runner_event(job_id, x_job_token, e.stage, e.text)
    return {"ok": True}


@app.post("/api/runner/{job_id}/result")
def runner_result(job_id: str, payload: dict, x_job_token: str = Header("")):
    return jobs.runner_result(job_id, x_job_token, payload)


@app.get("/api/runner/{job_id}/status")
def runner_status(job_id: str, x_job_token: str = Header("")):
    return jobs.runner_status(job_id, x_job_token)


@app.post("/api/runner/{job_id}/done")
def runner_done(job_id: str, d: RunnerDone, x_job_token: str = Header("")):
    return jobs.runner_done(job_id, x_job_token, d.pr_url, d.error)


@app.get("/")
def index():
    return FileResponse(config.ROOT / "frontend" / "v2" / "index.html")


@app.get("/classic")
def classic():
    return FileResponse(config.ROOT / "frontend" / "index.html")


app.mount("/static", StaticFiles(directory=config.ROOT / "frontend"), name="static")
