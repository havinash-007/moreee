"""Thin GitHub REST client. Reads are cheap and cached briefly; writes require an explicit token."""
import hashlib
import time

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


def get(path: str, params: dict | None = None, token: str | None = None):
    who = hashlib.sha256((token or auth.current_token.get() or "").encode()).hexdigest()[:12]
    key = f"{who}:{path}?{sorted((params or {}).items())}"  # never share cached reads between users
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    r = httpx.get(f"{API}{path}", params=params, headers=_headers(token), timeout=20)
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
    """Cheap keyword scan of policy files. A hit means 'a human must read this', not a verdict."""
    found, flags = [], []
    for f in POLICY_FILES:
        txt = raw_file(owner, repo, f)
        if not txt:
            continue
        found.append(f)
        low = txt.lower()
        if "ai" in low or "llm" in low or "copilot" in low:
            for line in txt.splitlines():
                l = line.lower()
                if ("ai" in l.split() or "llm" in l or "ai-" in l or "ai " in l) and any(w in l for w in BAN_WORDS):
                    flags.append({"file": f, "line": line.strip()[:240]})
    legal = []
    for f in found:
        t = (raw_file(owner, repo, f) or "").lower()
        if "signed-off-by" in t or "dco" in t:
            legal.append("DCO")
        if "cla" in t.split() or "contributor license" in t or "easycla" in t:
            legal.append("CLA")
    return {"files": found, "ai_flags": flags[:5], "legal": sorted(set(legal))}


def candidate_issues(owner: str, repo: str, labels=("good first issue", "help wanted"), limit=15) -> list[dict]:
    """Deterministic pre-filter: open, unassigned, not a PR, labelled, recent. No model tokens spent."""
    out: dict[int, dict] = {}
    for label in labels:
        items = get(f"/repos/{owner}/{repo}/issues",
                    {"state": "open", "labels": label, "assignee": "none", "per_page": 30, "sort": "updated"})
        for i in items:
            if "pull_request" in i or i.get("assignee"):
                continue
            out[i["number"]] = {
                "number": i["number"], "title": i["title"], "url": i["html_url"],
                "labels": [l["name"] for l in i.get("labels", [])],
                "comments": i.get("comments", 0), "updated": i["updated_at"],
                "body": (i.get("body") or "")[:1500],
            }
    # fewer comments = less likely already claimed/discussed to death
    return sorted(out.values(), key=lambda x: x["comments"])[:limit]


def has_open_pr_for(owner: str, repo: str, number: int) -> bool:
    try:
        r = get("/search/issues", {"q": f"repo:{owner}/{repo} is:pr {number} in:body,title"})
    except httpx.HTTPStatusError:
        return True  # when unsure, treat as claimed
    return r.get("total_count", 0) > 0


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
