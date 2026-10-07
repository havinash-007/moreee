"""The mentor's agents. Each one does as much as possible in plain code and calls the model once, with a capped output."""
import json

from . import github, llm

# ---------------------------------------------------------------- scout

SCOUT_SYSTEM = """You are a scout helping a student pick a first open-source issue.
You get the student's profile and pre-filtered candidate issues (already open, unassigned, labelled).
Rank the best 3 for THIS student. Prefer small, clear, testable fixes that match their languages and time.
Reply with JSON only: {"picks":[{"repo":"owner/name","number":N,"fit":"one sentence","learn":"what they will learn","hours":N,"risk":"one sentence"}]}"""


def _org_repos(org: str, languages: list[str], n: int = 3) -> list[str]:
    try:
        repos = github.get(f"/orgs/{org}/repos", {"sort": "updated", "per_page": 30, "type": "public"})
    except github.httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            raise
        repos = github.get(f"/users/{org}/repos", {"sort": "updated", "per_page": 30})  # owner is a person, not an org
    want = {l.lower() for l in languages}
    ok = [r for r in repos if not r.get("archived") and not r.get("fork")]
    pref = [r for r in ok if (r.get("language") or "").lower() in want] or ok
    pref.sort(key=lambda r: r.get("open_issues_count", 0), reverse=True)
    return [r["full_name"] for r in pref[:n]]


def scout(org: str, profile: dict, session_id: str, repo: str | None = None) -> dict:
    pool, policies, skipped = [], {}, []
    for full in ([repo] if repo else _org_repos(org, profile.get("languages", []))):
        owner, repo = full.split("/")
        pol = github.policy_scan(owner, repo)
        policies[full] = pol
        if pol["ai_flags"] and profile.get("mode") == "full":
            skipped.append({"repo": full, "reason": "Policy mentions AI restrictions; full-auto skips these", "flags": pol["ai_flags"]})
            continue
        for i in github.candidate_issues(owner, repo)[:6]:
            if github.has_open_pr_for(owner, repo, i["number"]):
                continue
            i["repo"] = full
            pool.append(i)
    pool = pool[:8]
    if not pool:
        return {"picks": [], "skipped": skipped, "policies": policies, "cost_usd": 0.0}
    brief = [{"repo": i["repo"], "number": i["number"], "title": i["title"], "labels": i["labels"],
              "comments": i["comments"], "body": i["body"][:500]} for i in pool]
    user = json.dumps({"student": profile, "candidates": brief})
    r = llm.ask(tier="cheap", system=SCOUT_SYSTEM, messages=[{"role": "user", "content": user}],
                max_tokens=900, session_id=session_id)
    by = {(i["repo"], i["number"]): i for i in pool}
    picks = []
    for p in llm.parse_json(r["text"]).get("picks", []):
        src = by.get((p.get("repo"), p.get("number")))
        if src:
            picks.append({**p, "title": src["title"], "url": src["url"], "labels": src["labels"],
                          "legal": policies[src["repo"]]["legal"], "ai_flags": policies[src["repo"]]["ai_flags"]})
    return {"picks": picks, "skipped": skipped, "policies": policies, "cost_usd": r["cost_usd"]}


# ------------------------------------------------------------ explainer

TOUR_SYSTEM = """You teach a student a repository in plain language. Use ONLY the material given; if something is unknown, say so.
Write markdown with these sections: What it is; Architecture (a mermaid flowchart of components you can infer);
Directory map (one line each); How to build and test (only commands found in the material); Conventions and sign-offs;
Files to read first (max 5, from the directory listing); 3 check questions. Be concise: under 700 words."""


def tour(full_name: str, issue_title: str, level: str, session_id: str) -> dict:
    owner, repo = full_name.split("/")
    ov = github.repo_overview(owner, repo)
    user = f"Student level: {level}\nIssue they will work on: {issue_title}\nRepo: {full_name}\n{json.dumps(ov)}"
    r = llm.ask(tier="smart", system=TOUR_SYSTEM, messages=[{"role": "user", "content": user}],
                max_tokens=1800, session_id=session_id, effort="low")
    return {"markdown": r["text"], "cost_usd": r["cost_usd"], "cached": r["cached"], "overview": ov}


# ---------------------------------------------------------------- coach

COACH_LEARN = """You are a patient open-source coach. The STUDENT writes the code.
Hint ladder: level 1 a guiding question, level 2 a pointer to a file/function, level 3 (only if the student is stuck) an approach in words.
Never write the full fix. Ask them to explain their idea first. Keep replies under 150 words."""

COACH_SEMI = """You are a pair programmer for a student using AI to move fast, but they must understand everything.
Give small, commit-sized chunks (a failing test first, then the smallest fix) with short code. After each chunk ask ONE question
("what does this do?", "what input breaks it?") and wait for the answer. Ask them to change something themselves. Under 200 words plus code."""


def coach(mode: str, context: str, history: list[dict], session_id: str) -> dict:
    system = (COACH_LEARN if mode == "learn" else COACH_SEMI) + "\n\nProject context:\n" + context[:6000]
    msgs = history[-6:]  # trimmed history keeps cost flat as the chat grows
    r = llm.ask(tier="smart", system=system, messages=msgs, max_tokens=700,
                session_id=session_id, effort="low", use_cache=False)
    return {"reply": r["text"], "cost_usd": r["cost_usd"]}
