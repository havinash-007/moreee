"""Reply drafting for reviewer/maintainer comments on a student's PR.

Pipeline (2 model calls per PR check, regardless of how many comments):
  1. plain code: fetch comments, drop the PR author's own, bots, and ones already handled
  2. one CHEAP call classifies every new comment
  3. one SMART call drafts replies for the ones that need an answer
Nothing is posted unless the operator set AUTO_POST_REPLIES=true AND the caller approves the specific ids.
"""
import json

from . import config, github, llm

STATE = config.DATA / "replies.json"

CLASSIFY_SYSTEM = """Classify each pull-request comment. Reply with JSON only: {"items":[{"id":N,"kind":"actionable|question|nit|praise|other","needs_code":true|false}]}
actionable = asks for a change; question = asks something; nit = tiny style remark; praise = thanks/approval; other = anything else."""

DRAFT_SYSTEM = """You write short, polite replies from a student contributor to maintainers' comments on their pull request.
Rules: be concise and humble; thank them once; never promise what is not done; if code must change, say what you will change and that you will push an update;
if you are not sure, ask a clarifying question; never claim tests passed unless told so. No emojis.
Reply with JSON only: {"replies":[{"id":N,"reply":"text"}]}"""


def _load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    STATE.write_text(json.dumps(d, indent=1))


def parse_pr(url: str) -> tuple[str, str, int]:
    parts = url.rstrip("/").split("/")
    i = parts.index("pull")
    return parts[i - 2], parts[i - 1], int(parts[i + 1])


def fetch_new_comments(owner: str, repo: str, number: int) -> tuple[list[dict], str]:
    pr = github.get(f"/repos/{owner}/{repo}/pulls/{number}")
    author = pr["user"]["login"]
    state = _load().get(f"{owner}/{repo}#{number}", {})
    seen = set(state.get("handled", []))
    comments = []
    for c in github.get(f"/repos/{owner}/{repo}/pulls/{number}/comments", {"per_page": 100}):
        comments.append({"id": c["id"], "kind_src": "review", "user": c["user"]["login"], "bot": c["user"]["type"] == "Bot",
                         "body": c["body"][:1200], "path": c.get("path"), "diff": (c.get("diff_hunk") or "")[-400:]})
    for c in github.get(f"/repos/{owner}/{repo}/issues/{number}/comments", {"per_page": 100}):
        comments.append({"id": c["id"], "kind_src": "issue", "user": c["user"]["login"], "bot": c["user"]["type"] == "Bot",
                         "body": c["body"][:1200], "path": None, "diff": ""})
    fresh = [c for c in comments if c["user"] != author and not c["bot"] and c["id"] not in seen]
    return fresh, pr["title"]


def _ai_flags(owner: str, repo: str) -> list[dict]:
    return github.policy_scan(owner, repo)["ai_flags"]


def draft(pr_url: str, session_id: str) -> dict:
    owner, repo, number = parse_pr(pr_url)
    fresh, title = fetch_new_comments(owner, repo, number)
    if not fresh:
        return {"drafts": [], "note": "No new comments to answer.", "cost_usd": 0.0}
    cost = 0.0
    c = llm.ask(tier="cheap", system=CLASSIFY_SYSTEM, max_tokens=500, session_id=session_id,
                messages=[{"role": "user", "content": json.dumps([{"id": x["id"], "text": x["body"][:400]} for x in fresh])}])
    cost += c["cost_usd"]
    kinds = {i["id"]: i for i in llm.parse_json(c["text"]).get("items", [])}
    need = [x for x in fresh if kinds.get(x["id"], {}).get("kind") not in ("praise",)]
    replies = {}
    if need:
        payload = {"pr_title": title, "comments": [{"id": x["id"], "from": x["user"], "file": x["path"],
                                                       "code": x["diff"], "text": x["body"]} for x in need]}
        d = llm.ask(tier="smart", system=DRAFT_SYSTEM, max_tokens=900, session_id=session_id, effort="low",
                    messages=[{"role": "user", "content": json.dumps(payload)}])
        cost += d["cost_usd"]
        replies = {r["id"]: r["reply"] for r in llm.parse_json(d["text"]).get("replies", [])}
    out = []
    for x in fresh:
        k = kinds.get(x["id"], {})
        out.append({"id": x["id"], "source": x["kind_src"], "user": x["user"], "comment": x["body"], "path": x["path"],
                    "kind": k.get("kind", "other"), "needs_code": bool(k.get("needs_code")),
                    "reply": replies.get(x["id"], "")})
    state = _load()
    state.setdefault(f"{owner}/{repo}#{number}", {}).setdefault("handled", [])
    _save(state)
    flags = _ai_flags(owner, repo)
    return {"drafts": out, "pr": {"owner": owner, "repo": repo, "number": number}, "ai_flags": flags,
            "can_post": config.AUTO_POST_REPLIES and bool(config.GITHUB_TOKEN) and not flags, "cost_usd": cost}


def send(pr_url: str, items: list[dict], disclose: bool = True) -> dict:
    """items: [{id, source, reply}] with the (possibly edited) text the human approved."""
    if not config.AUTO_POST_REPLIES:
        raise PermissionError("Posting is disabled. Set AUTO_POST_REPLIES=true on the server to enable it.")
    if not config.GITHUB_TOKEN:
        raise PermissionError("GITHUB_TOKEN is not set.")
    owner, repo, number = parse_pr(pr_url)
    if _ai_flags(owner, repo):
        raise PermissionError("This project's policy restricts AI-generated messages. Copy the draft, rewrite it in your own words, and post it yourself.")
    state = _load()
    key = f"{owner}/{repo}#{number}"
    sent = []
    for it in items:
        body = it["reply"].strip()
        if not body:
            continue
        if disclose and config.AI_DISCLOSURE:
            body += f"\n\n_{config.AI_DISCLOSURE}_"
        if it["source"] == "review":
            github.post(f"/repos/{owner}/{repo}/pulls/{number}/comments/{it['id']}/replies", {"body": body})
        else:
            github.post(f"/repos/{owner}/{repo}/issues/{number}/comments", {"body": body})
        state.setdefault(key, {}).setdefault("handled", []).append(it["id"])
        sent.append(it["id"])
    _save(state)
    return {"sent": sent}
