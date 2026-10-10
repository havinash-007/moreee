"""Thin GitHub REST client. Reads are cheap and cached briefly; writes require an explicit token."""
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

from . import auth, config

API = "https://api.github.com"
_cache: dict[str, tuple[float, object]] = {}
TTL = 300


def _headers(token: str | None = None) -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    t = token or auth.current_token.get() or config.GITHUB_TOKEN
    if t:
        h["Authorization"] = f"Bearer {t}"
    return h


def _send(method: str, url: str, attempts: int = 3, **kw) -> httpx.Response:
    """One GitHub request, retried on network errors, 5xx and rate-limit responses (honouring Retry-After / reset, capped at 15s)."""
    for n in range(attempts):
        last = n == attempts - 1
        try:
            r = httpx.request(method, url, timeout=20, **kw)
        except httpx.TransportError:
            if last:
                raise
            time.sleep(1 + n)
            continue
        limited = r.status_code == 429 or (r.status_code == 403 and (r.headers.get("retry-after") or r.headers.get("x-ratelimit-remaining") == "0"))
        if (limited or r.status_code >= 500) and not last:
            wait = r.headers.get("retry-after")
            if wait is None and limited and r.headers.get("x-ratelimit-reset"):
                wait = int(r.headers["x-ratelimit-reset"]) - time.time()
            time.sleep(min(max(float(wait or 1 + n), 1), 15))
            continue
        return r
    return r


def get(path: str, params: dict | None = None, token: str | None = None):
    who = hashlib.sha256((token or auth.current_token.get() or "").encode()).hexdigest()[:12]
    key = f"{who}:{path}?{sorted((params or {}).items())}"  # never share cached reads between users
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    r = _send("GET", f"{API}{path}", params=params, headers=_headers(token))
    r.raise_for_status()
    data = r.json()
    _cache[key] = (time.time(), data)
    return data


def post(path: str, body: dict, token: str | None = None):
    r = httpx.post(f"{API}{path}", json=body, headers=_headers(token), timeout=20)
    r.raise_for_status()
    return r.json()


def raw_file(owner: str, repo: str, path: str) -> str | None:
    try:
        data = get(f"/repos/{owner}/{repo}/contents/{path}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None  # file genuinely absent
        raise  # rate limit / auth / outage must NOT look like "no policy found"
    if isinstance(data, dict) and data.get("encoding") == "base64":
        import base64
        return base64.b64decode(data["content"]).decode("utf-8", "replace")
    return None


POLICY_FILES = [".github/AI_POLICY.md", "AI_POLICY.md", "AGENTS.md", "CONTRIBUTING.md", ".github/CONTRIBUTING.md"]
BAN_WORDS = ("no ai", "not accept ai", "ban ai", "prohibit", "not allowed", "will be closed", "do not use ai", "ai-generated")


def policy_scan(owner: str, repo: str) -> dict:
    """Cheap keyword scan of policy files (each fetched once). A hit means 'a human must read this', not a verdict."""
    texts = {f: raw_file(owner, repo, f) for f in POLICY_FILES}
    found = [f for f, t in texts.items() if t]
    flags, legal = [], set()
    for f in found:
        txt = texts[f]
        low = txt.lower()
        if "ai" in low or "llm" in low or "copilot" in low:
            for line in txt.splitlines():
                l = line.lower()
                if ("ai" in l.split() or "llm" in l or "ai-" in l or "ai " in l) and any(w in l for w in BAN_WORDS):
                    flags.append({"file": f, "line": line.strip()[:240]})
        if "signed-off-by" in low or "dco" in low:
            legal.add("DCO")
        if "cla" in low.split() or "contributor license" in low or "easycla" in low:
            legal.add("CLA")
    return {"files": found, "ai_flags": flags[:5], "legal": sorted(legal)}


LABEL_TIERS = [
    ["good first issue", "good-first-issue", "first-timers-only", "beginner", "starter", "easy"],
    ["help wanted", "help-wanted", "contributions welcome"],
    None,  # last resort: any open, unassigned, unlinked issue; the ranking step judges suitability
]


def search_free_issues(scope: str, tier: int, limit: int = 40) -> tuple[list[dict], int]:
    """ONE search call: open, unassigned, no linked PR, not archived, optionally label-filtered.
    scope is 'org:x', 'user:x' or 'repo:x/y'. Replaces the old per-issue PR lookups that exhausted the search rate limit."""
    q = f"{scope} is:issue is:open no:assignee -linked:pr archived:false"
    labels = LABEL_TIERS[tier]
    if labels:
        q += " label:" + ",".join(f'"{l}"' for l in labels)
    else:
        q += " comments:<4"
    data = get("/search/issues", {"q": q, "sort": "updated", "order": "desc", "per_page": limit})
    out = []
    for i in data.get("items", []):
        out.append({
            "number": i["number"], "title": i["title"], "url": i["html_url"],
            "repo": i["repository_url"].split("/repos/")[1],
            "labels": [l["name"] for l in i.get("labels", [])], "comments": i.get("comments", 0),
            "updated": i["updated_at"], "body": (i.get("body") or "")[:1500],
        })
    return out, data.get("total_count", len(out))


CLAIM_RE = re.compile(r"(i('| wi)?ll (take|work|do|fix|pick)|i can (take|work|fix|do)|working on (this|it)|can i (work|take|pick|have)|"
                      r"assign (this )?(to|me)|i('d| would) (like|love) to (work|take|fix)|i want to (work|fix|take)|claim(ing)?( this)?)", re.I)


def recent_claim(owner: str, repo: str, number: int, days: int = 14) -> bool:
    """True if someone (not just the author) recently said they are working on it."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        cs = get(f"/repos/{owner}/{repo}/issues/{number}/comments", {"since": since, "per_page": 30})
    except httpx.HTTPStatusError:
        return False  # a failed read here must not hide the issue; the verify step re-checks on click
    return any(CLAIM_RE.search(c.get("body") or "") for c in cs)


def verify_issue(owner: str, repo: str, number: int, light: bool = False) -> dict:
    """Check an issue against what is true right now: open, unassigned, no open PR referencing it, nobody claiming it.
    light=True (used while scouting) trusts the search for open/unassigned and skips the uncached issue fetch."""
    if light:
        i = {"state": "open", "assignees": []}
    else:
        _cache.clear()
        i = get(f"/repos/{owner}/{repo}/issues/{number}")
    linked = []
    try:
        for ev in get(f"/repos/{owner}/{repo}/issues/{number}/timeline", {"per_page": 100}):
            src = (ev.get("source") or {}).get("issue") or {}
            if ev.get("event") == "cross-referenced" and "pull_request" in src and src.get("state") == "open":
                linked.append(src["number"])
    except httpx.HTTPStatusError:
        pass
    claimed = recent_claim(owner, repo, number)
    ok = i.get("state") == "open" and not i.get("assignees") and not linked and not claimed
    reason = ("closed" if i.get("state") != "open" else "assigned" if i.get("assignees") else
              f"an open pull request already references it (#{linked[0]})" if linked else "someone said they are working on it" if claimed else "")
    return {"ok": ok, "reason": reason, "checked_at": datetime.now(timezone.utc).isoformat(), "linked_prs": linked}


def repo_overview(owner: str, repo: str) -> dict:
    info = get(f"/repos/{owner}/{repo}")
    tree = get(f"/repos/{owner}/{repo}/contents/")
    names = [("dir/" if t["type"] == "dir" else "") + t["name"] for t in tree] if isinstance(tree, list) else []
    return {
        "description": info.get("description"), "language": info.get("language"),
        "stars": info.get("stargazers_count"), "default_branch": info.get("default_branch"),
        "top_level": names[:80],
        "readme": (raw_file(owner, repo, "README.md") or "")[:4000],
        "contributing": (raw_file(owner, repo, "CONTRIBUTING.md") or raw_file(owner, repo, ".github/CONTRIBUTING.md") or "")[:3000],
    }


TOPICS = {
    "web": ["web", "frontend"], "ai-ml-data": ["machine-learning", "data-science"],
    "cloud-devops": ["devops", "kubernetes"], "security": ["security"], "mobile": ["android", "mobile"],
    "devtools": ["developer-tools", "cli"], "education": ["education"],
    "social": ["social-good", "hacktoberfest"], "creative": ["game-engine", "creative-coding"],
}


def discover(languages: list[str], interests: list[str], known: set[str], limit: int = 12) -> list[dict]:
    """Live search for active repos with open good-first-issues, grouped by owner.
    GitHub's search qualifiers do the filtering (no model tokens). Results are unrated and unverified."""
    from datetime import date, timedelta
    since = (date.today() - timedelta(days=90)).isoformat()
    langs = (languages or [None])[:2]
    topics = [t for i in (interests or [])[:2] for t in TOPICS.get(i, [])[:1]] or [None]
    seen: dict[str, dict] = {}
    for lang in langs:
        for topic in topics[:2]:
            q = f"good-first-issues:>3 stars:>200 pushed:>{since} archived:false fork:false"
            if lang:
                q += f" language:{lang}"
            if topic:
                q += f" topic:{topic}"
            data = get("/search/repositories", {"q": q, "sort": "help-wanted-issues", "order": "desc", "per_page": 15})
            for r in data.get("items", []):
                owner = r["owner"]["login"]
                if owner.lower() in known or r.get("full_name") in seen:
                    continue
                seen[r["full_name"]] = {
                    "repo": r["full_name"], "owner": owner, "description": (r.get("description") or "")[:200],
                    "language": r.get("language"), "stars": r.get("stargazers_count", 0),
                    "pushed": (r.get("pushed_at") or "")[:10], "topics": (r.get("topics") or [])[:5],
                    "license": (r.get("license") or {}).get("spdx_id"), "url": r["html_url"],
                    "open_issues": r.get("open_issues_count", 0), "matched": {"language": lang, "topic": topic},
                }
    # one repo per owner, most-starred first, so the list shows variety rather than one org's whole portfolio
    best: dict[str, dict] = {}
    for r in sorted(seen.values(), key=lambda x: x["stars"], reverse=True):
        best.setdefault(r["owner"].lower(), r)
    return list(best.values())[:limit]
