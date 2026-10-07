"""The mentor's agents. Each one does as much as possible in plain code and calls the model once, with a capped output."""
import json
from datetime import datetime, timezone

from . import github, llm

# ---------------------------------------------------------------- scout

SCOUT_SYSTEM = """You are a scout helping a student pick a first open-source issue.
You get the student's profile and pre-filtered candidate issues (already open, unassigned, labelled).
Rank the best 3 for THIS student. Prefer small, clear, testable fixes that match their languages and time.
Reply with JSON only: {"picks":[{"repo":"owner/name","number":N,"fit":"one sentence","learn":"what they will learn","hours":N,"risk":"one sentence"}]}"""


def _scope(owner: str, repo: str | None) -> str:
    return f"repo:{repo}" if repo else f"user:{owner}"  # `user:` matches repos owned by a person or an organisation


def scout_stream(org: str, profile: dict, session_id: str, repo: str | None = None, fallbacks: list[str] | None = None):
    """Yield progress events, then a final {'type': 'result', ...}. Tries the chosen organisation first, then up to two
    fallbacks, and only gives up after three. Deterministic work is plain code; the model is called once per attempt."""
    targets = [(org, repo)] + [(f, None) for f in (fallbacks or []) if f.lower() != org.lower()][:2]
    stats = {"tried": [], "found": 0, "claimed": 0, "has_pr": 0, "policy_skipped": 0}
    all_skipped, policies = [], {}
    step = lambda t: {"type": "step", "text": t}

    for owner, only_repo in targets:
        name = only_repo or owner
        stats["tried"].append(name)
        yield step(f"Searching {name} for open issues nobody has taken…")
        issues, total, tier = [], 0, 0
        for tier in range(len(github.LABEL_TIERS)):
            issues, total = github.search_free_issues(_scope(owner, only_repo), tier)
            if issues:
                break
            yield step("No beginner-labelled issues yet; widening the search…")
        if not issues:
            yield step(f"Nothing open and unclaimed in {name}.")
            continue
        stats["found"] += total
        yield step(f"Found {total} open, unassigned issues with no linked pull request.")

        # spread across repos, fewer comments first (less likely to be a long debate)
        issues.sort(key=lambda i: (i["comments"], i["updated"]), reverse=False)
        by_repo: dict[str, list[dict]] = {}
        for i in issues:
            by_repo.setdefault(i["repo"], []).append(i)
        repos = sorted(by_repo, key=lambda r: len(by_repo[r]), reverse=True)[:4]

        pool = []
        for full in repos:
            o, r = full.split("/")
            yield step(f"Reading {full} contribution and AI policies…")
            pol = policies.setdefault(full, github.policy_scan(o, r))
            if pol["ai_flags"] and profile.get("mode") == "full":
                all_skipped.append({"repo": full, "reason": "Policy mentions AI restrictions; full-auto skips these", "flags": pol["ai_flags"]})
                stats["policy_skipped"] += 1
                continue
            for i in by_repo[full][:5]:
                pool.append(i)
        yield step("Double-checking each issue for open PRs and people already working on it…")
        free = []
        for i in pool[:10]:
            o, r = i["repo"].split("/")
            v = github.verify_issue(o, r, i["number"], light=True)
            if v["ok"]:
                i["verified_at"] = v["checked_at"]
                free.append(i)
            elif "pull request" in v["reason"]:
                stats["has_pr"] += 1
            else:
                stats["claimed"] += 1
        free = free[:8]
        if not free:
            yield step(f"Everything in {name} looks taken; trying the next best match…")
            continue

        yield step(f"Ranking {len(free)} candidates for you…")
        brief = [{"repo": i["repo"], "number": i["number"], "title": i["title"], "labels": i["labels"],
                  "comments": i["comments"], "body": i["body"][:500]} for i in free]
        r = llm.ask(tier="cheap", system=SCOUT_SYSTEM, messages=[{"role": "user", "content": json.dumps({"student": profile, "candidates": brief})}],
                    max_tokens=900, session_id=session_id)
        by = {(i["repo"], i["number"]): i for i in free}
        picks = []
        for p in llm.parse_json(r["text"]).get("picks", []):
            src = by.get((p.get("repo"), p.get("number")))
            if src:
                picks.append({**p, "title": src["title"], "url": src["url"], "labels": src["labels"],
                              "legal": policies[src["repo"]]["legal"], "ai_flags": policies[src["repo"]]["ai_flags"],
                              "verified_at": src.get("verified_at") or datetime.now(timezone.utc).isoformat()})
        if picks:
            yield {"type": "result", "picks": picks, "skipped": all_skipped, "policies": policies, "stats": stats,
                   "org_used": name, "cost_usd": r["cost_usd"]}
            return
        yield step("Could not rank any of those; trying the next best match…")

    yield {"type": "result", "picks": [], "skipped": all_skipped, "policies": policies, "stats": stats, "org_used": None, "cost_usd": 0.0}


def scout(org: str, profile: dict, session_id: str, repo: str | None = None, fallbacks: list[str] | None = None) -> dict:
    last = {}
    for ev in scout_stream(org, profile, session_id, repo, fallbacks):
        last = ev
    return last


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
