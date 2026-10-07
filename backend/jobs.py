"""Full-auto jobs (Option A: the worker runs on the student's own machine).

The web app never runs a stranger's code and never holds the student's GitHub token for this feature:
  student clicks Full-auto -> pre-flight gates -> job + one-time token
  -> student runs the local runner (backend/runner.py) with that token
  -> runner streams progress and uploads a diff for REVIEW
  -> student edits the PR text and approves -> the runner (their own gh login) commits, pushes to THEIR fork, opens the PR.
Nothing is opened without an explicit approval click.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid

from . import db, github

ACTIVE = ("ready", "running", "review", "approved", "opening")
TERMINAL = ("done", "failed", "cancelled", "expired")
TRANSITIONS = {
    "ready": {"running", "cancelled", "expired", "failed"},
    "running": {"review", "failed", "cancelled"},
    "review": {"approved", "cancelled", "failed"},
    "approved": {"opening", "done", "failed", "cancelled"},
    "opening": {"done", "failed"},
}
MAX_PER_DAY = int(os.getenv("MAX_JOBS_PER_DAY", "3"))
READY_TTL = 2 * 3600
MAX_DIFF = 300_000
MAX_EVENTS = 500
SECRET_PATTERNS = [r"sk-ant-[A-Za-z0-9_-]{20,}", r"gh[pousr]_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}", r"AKIA[0-9A-Z]{16}",
                   r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", r"xox[baprs]-[A-Za-z0-9-]{20,}"]


class JobError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def new_token() -> str:
    """One-time runner token. The fixed prefix matters: token_urlsafe can start with '-', which the command line would read as an option."""
    return "jt_" + secrets.token_urlsafe(32)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _row(r) -> dict:
    d = dict(r)
    for k in ("legal", "result", "warnings"):
        d[k] = json.loads(d[k] or ("{}" if k == "result" else "[]"))
    d.pop("token_hash", None)
    return d


def _expire(con) -> None:
    con.execute("UPDATE jobs SET status='expired', updated=? WHERE status='ready' AND created < ?", (time.time(), time.time() - READY_TTL))


def _event(con, job_id: str, kind: str, text: str) -> None:
    n = con.execute("SELECT COUNT(*) FROM events WHERE job_id=?", (job_id,)).fetchone()[0]
    if n >= MAX_EVENTS:
        return
    con.execute("INSERT INTO events(job_id, ts, kind, text) VALUES (?,?,?,?)", (job_id, time.time(), kind, text[:400]))


def _move(con, job: dict, new: str, **fields) -> None:
    if new not in TRANSITIONS.get(job["status"], set()):
        raise JobError(f"Cannot go from {job['status']} to {new}.", 409)
    sets = ", ".join(f"{k}=?" for k in fields)
    con.execute(f"UPDATE jobs SET status=?, updated=?{', ' + sets if sets else ''} WHERE id=?", (new, time.time(), *fields.values(), job["id"]))


# --------------------------------------------------------------------------- student side
def create(user: str, repo: str, number: int, title: str, consent: bool, signoff: bool) -> dict:
    """Pre-flight gates, then a job and a one-time runner token. Every gate blocks; none is advisory."""
    if not consent:
        raise JobError("You need to confirm that you understand an AI will write this change and that you are responsible for it.", 400)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or ""):
        raise JobError("That is not a valid repository.", 400)
    owner, name = repo.split("/")
    with db.connect() as con:
        _expire(con)
        if con.execute("SELECT 1 FROM jobs WHERE user=? AND status IN (%s)" % ",".join("?" * len(ACTIVE)), (user, *ACTIVE)).fetchone():
            raise JobError("You already have a job in progress. Finish or cancel it first.", 409)
        if con.execute("SELECT COUNT(*) FROM jobs WHERE user=? AND created > ?", (user, time.time() - 86400)).fetchone()[0] >= MAX_PER_DAY:
            raise JobError(f"Daily limit reached ({MAX_PER_DAY} automated jobs). Quality beats volume.", 429)

    pol = github.policy_scan(owner, name)
    if pol["ai_flags"]:
        raise JobError("This project's policy restricts AI-generated contributions, so Full-auto is blocked for it. Use Learn mode instead. Policy line: " + pol["ai_flags"][0]["line"][:200], 403)
    v = github.verify_issue(owner, name, int(number))
    if not v["ok"]:
        raise JobError(f"This issue is no longer free: {v['reason']}.", 409)

    token = new_token()
    jid = uuid.uuid4().hex[:12]
    now = time.time()
    with db.connect() as con:
        con.execute("INSERT INTO jobs(id,user,repo,number,title,status,stage,created,updated,token_hash,signoff,legal) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (jid, user, repo, int(number), (title or "")[:300], "ready", "waiting for runner", now, now, _hash(token), int(bool(signoff)), json.dumps(pol["legal"])))
        _event(con, jid, "info", "Pre-flight checks passed: policy read, issue verified free.")
        con.commit()
    return {"id": jid, "token": token, "legal": pol["legal"], "expires_in": READY_TTL}


def get(user: str, job_id: str, since: int = 0) -> dict:
    with db.connect() as con:
        _expire(con)
        r = con.execute("SELECT * FROM jobs WHERE id=? AND user=?", (job_id, user)).fetchone()
        if not r:
            raise JobError("No such job.", 404)
        ev = con.execute("SELECT id, ts, kind, text FROM events WHERE job_id=? AND id>? ORDER BY id", (job_id, since)).fetchall()
    return {**_row(r), "events": [dict(e) for e in ev]}


def list_for(user: str) -> list[dict]:
    with db.connect() as con:
        _expire(con)
        rows = con.execute("SELECT * FROM jobs WHERE user=? ORDER BY created DESC LIMIT 20", (user,)).fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["result"] = {}  # keep the list light
        out.append(d)
    return out


def approve(user: str, job_id: str, pr_title: str, pr_body: str, cla_confirmed: bool) -> dict:
    with db.connect() as con:
        r = con.execute("SELECT * FROM jobs WHERE id=? AND user=?", (job_id, user)).fetchone()
        if not r:
            raise JobError("No such job.", 404)
        job = _row(r)
        if job["status"] != "review":
            raise JobError(f"This job is {job['status']}, not waiting for your review.", 409)
        if any(w.startswith("secret:") for w in job["warnings"]):
            raise JobError("The change appears to contain a secret (key or token). It cannot be opened as a PR.", 422)
        if "CLA" in job["legal"] and not cla_confirmed:
            raise JobError("This project requires a CLA. Sign it yourself first, then tick the box.", 422)
        pr_title, pr_body = (pr_title or "").strip(), (pr_body or "").strip()
        if not pr_title or len(pr_title) > 200:
            raise JobError("Give the PR a title (up to 200 characters).", 422)
        if len(pr_body) < 20 or len(pr_body) > 8000:
            raise JobError("Write the PR description in your own words (20 to 8000 characters).", 422)
        _move(con, job, "approved", pr_title=pr_title, pr_body=pr_body, stage="approved: runner will open the PR")
        _event(con, job_id, "info", "You approved the change. The runner will open the PR from your fork.")
        con.commit()
    return get(user, job_id)


def cancel(user: str, job_id: str) -> dict:
    with db.connect() as con:
        r = con.execute("SELECT * FROM jobs WHERE id=? AND user=?", (job_id, user)).fetchone()
        if not r:
            raise JobError("No such job.", 404)
        job = _row(r)
        if job["status"] in TERMINAL:
            return get(user, job_id)
        _move(con, job, "cancelled", stage="cancelled")
        _event(con, job_id, "info", "Cancelled by you.")
        con.commit()
    return get(user, job_id)


# --------------------------------------------------------------------------- runner side (authenticated by the one-time token)
def authenticate(job_id: str, token: str) -> dict:
    with db.connect() as con:
        _expire(con)
        r = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r or not hmac.compare_digest(r["token_hash"], _hash(token or "")):
        raise JobError("Invalid job token.", 403)
    return _row(r)


def spec(job_id: str, token: str) -> dict:
    j = authenticate(job_id, token)
    if j["status"] in TERMINAL:
        raise JobError(f"This job is {j['status']}.", 410)
    return {"id": j["id"], "repo": j["repo"], "number": j["number"], "title": j["title"], "legal": j["legal"], "signoff": bool(j["signoff"]),
            "issue_url": f"https://github.com/{j['repo']}/issues/{j['number']}"}


def runner_event(job_id: str, token: str, stage: str, text: str) -> None:
    j = authenticate(job_id, token)
    if j["status"] in TERMINAL:
        raise JobError(f"This job is {j['status']}.", 410)
    with db.connect() as con:
        if j["status"] == "ready":
            _move(con, j, "running")
        if stage:
            con.execute("UPDATE jobs SET stage=?, updated=? WHERE id=?", (stage[:80], time.time(), job_id))
        _event(con, job_id, "step", text)
        con.commit()


def runner_result(job_id: str, token: str, payload: dict) -> dict:
    j = authenticate(job_id, token)
    if j["status"] not in ("running", "ready"):
        raise JobError(f"This job is {j['status']}.", 409)
    status = payload.get("status")
    if status not in ("fixed", "stopped"):
        raise JobError("status must be 'fixed' or 'stopped'.", 422)
    diff = str(payload.get("diff") or "")
    truncated = len(diff) > MAX_DIFF
    diff = diff[:MAX_DIFF]
    warnings = [f"secret:{p[:20]}" for p in SECRET_PATTERNS if re.search(p, diff)]
    if truncated:
        warnings.append("diff truncated at 300 KB")
    lst = lambda k, n=20: [str(x)[:300] for x in (payload.get(k) or [])][:n]
    result = {"status": status, "summary": str(payload.get("summary") or "")[:3000], "diff": diff, "files": lst("files", 60),
              "tests_run": lst("tests_run"), "not_verified": lst("not_verified"), "turns": int(payload.get("turns") or 0), "cost_usd": float(payload.get("cost_usd") or 0)}
    ok = status == "fixed" and diff.strip()
    with db.connect() as con:
        if j["status"] == "ready":
            _move(con, j, "running")
            j["status"] = "running"
        if ok:
            _move(con, j, "review", result=json.dumps(result), warnings=json.dumps(warnings), stage="waiting for your review",
                  pr_title=str(payload.get("pr_title") or j["title"])[:200], pr_body=str(payload.get("pr_body") or "")[:8000])
            _event(con, job_id, "info", "The worker finished. Review the change before anything is opened.")
        else:
            _move(con, j, "failed", result=json.dumps(result), warnings=json.dumps(warnings), stage="stopped",
                  error=(result["summary"] or "The worker could not produce a verified fix.")[:500])
            _event(con, job_id, "info", "The worker stopped without a verified fix. Nothing was changed upstream.")
        con.commit()
    return {"status": "review" if ok else "failed"}


def runner_status(job_id: str, token: str) -> dict:
    j = authenticate(job_id, token)
    return {"status": j["status"], "pr_title": j["pr_title"], "pr_body": j["pr_body"], "signoff": bool(j["signoff"])}


def runner_done(job_id: str, token: str, pr_url: str | None, error: str | None) -> dict:
    j = authenticate(job_id, token)
    with db.connect() as con:
        if j["status"] == "approved":
            _move(con, j, "opening")
            j["status"] = "opening"
        if pr_url:
            if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/\d+", pr_url):
                raise JobError("That does not look like a GitHub PR URL.", 422)
            _move(con, j, "done", pr_url=pr_url, stage="done")
            _event(con, job_id, "info", "Pull request opened from your fork.")
        else:
            _move(con, j, "failed", error=(error or "The runner reported a failure.")[:500], stage="failed")
            _event(con, job_id, "info", "The runner stopped: " + (error or "unknown error")[:200])
        con.commit()
    return {"status": "done" if pr_url else "failed"}
