import json
from types import SimpleNamespace

import pytest

from backend import config, llm, matcher, replier


def fake_resp(text="ok", inp=1000, out=100, cr=0, cw=0):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=inp, output_tokens=out,
                              cache_read_input_tokens=cr, cache_creation_input_tokens=cw))


class FakeClient:
    def __init__(self, resp):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self.resp = resp

    def _create(self, **kw):
        self.calls.append(kw)
        return self.resp


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "USAGE_FILE", tmp_path / "usage.json")
    monkeypatch.setattr(llm, "ledger", llm.Ledger())
    fc = FakeClient(fake_resp())
    monkeypatch.setattr(llm, "_client", fc)
    return fc


# ---- matcher
PROFILE = dict(languages=["Python"], skill="beginner", interests=["web"], goal="hackathon",
               git_level="never", machine="low", legal="both")


def test_matcher_prefers_fit():
    top = matcher.rank(PROFILE, top=3)
    orgs = {o["name"]: o for o in matcher.catalogue()}
    assert all(0 <= t["total"] <= 55 for t in top)
    assert top[0]["total"] >= top[1]["total"] >= top[2]["total"]
    for t in top:  # a Python/web beginner on a low-spec laptop must not be sent to heavy, advanced projects
        assert "Python" in orgs[t["org"]]["languages"] and orgs[t["org"]]["beginner"] >= 3


def test_matcher_cla_gate():
    r = matcher.score_org(next(o for o in matcher.catalogue() if o["name"] == "Kubernetes"), {**PROFILE, "legal": "dco"})
    assert r["total"] == 0 and r["gate"]


# ---- llm: tiers, effort, caching, budget
def test_cheap_tier_has_no_effort_and_smart_does(isolated):
    llm.ask(tier="cheap", system="s", messages=[{"role": "user", "content": "a"}], max_tokens=50)
    llm.ask(tier="smart", system="s", messages=[{"role": "user", "content": "b"}], max_tokens=50)
    cheap, smart = isolated.calls
    assert cheap["model"] == config.MODEL_CHEAP and "output_config" not in cheap
    assert smart["model"] == config.MODEL_SMART and smart["output_config"] == {"effort": "low"}
    assert cheap["max_tokens"] == 50 and cheap["cache_control"] == {"type": "ephemeral"}


def test_disk_cache_is_free(isolated):
    a = llm.ask(tier="cheap", system="s", messages=[{"role": "user", "content": "same"}], max_tokens=50)
    b = llm.ask(tier="cheap", system="s", messages=[{"role": "user", "content": "same"}], max_tokens=50)
    assert a["cost_usd"] > 0 and b["cost_usd"] == 0 and b["cached"]
    assert len(isolated.calls) == 1


def test_session_budget_blocks(isolated, monkeypatch):
    monkeypatch.setattr(config, "SESSION_BUDGET_USD", 0.0001)
    with pytest.raises(llm.BudgetExceeded):
        llm.ask(tier="smart", system="s", messages=[{"role": "user", "content": "x"}], max_tokens=4000)
    assert isolated.calls == []  # blocked before spending anything


def test_cost_math():
    assert llm.cost_of("claude-haiku-4-5", 1_000_000, 0) == pytest.approx(1.0)
    assert llm.cost_of("claude-haiku-4-5", 0, 0, cache_read=1_000_000) == pytest.approx(0.1)
    assert llm.cost_of("unknown-model", 1_000_000, 0) == pytest.approx(config.DEFAULT_PRICE[0])


def test_parse_json_tolerates_prose():
    assert llm.parse_json('Sure! {"a": [1, 2]} done') == {"a": [1, 2]}


# ---- replier gating
def test_parse_pr():
    assert replier.parse_pr("https://github.com/o/r/pull/12/files") == ("o", "r", 12)


def test_send_disabled_by_default(monkeypatch):
    monkeypatch.setattr(config, "AUTO_POST_REPLIES", False)
    with pytest.raises(PermissionError):
        replier.send("https://github.com/o/r/pull/1", [{"id": 1, "source": "issue", "reply": "hi"}])


def test_send_blocked_when_policy_flags_ai(monkeypatch):
    monkeypatch.setattr(config, "AUTO_POST_REPLIES", True)
    monkeypatch.setattr(config, "GITHUB_TOKEN", "t")
    monkeypatch.setattr(replier, "_ai_flags", lambda o, r: [{"file": "AGENTS.md", "line": "no AI messages"}])
    posted = []
    monkeypatch.setattr(replier.github, "post", lambda *a, **k: posted.append(a))
    with pytest.raises(PermissionError):
        replier.send("https://github.com/o/r/pull/1", [{"id": 1, "source": "issue", "reply": "hi"}])
    assert posted == []


def test_send_needs_token(monkeypatch):
    monkeypatch.setattr(config, "AUTO_POST_REPLIES", True)
    monkeypatch.setattr(config, "GITHUB_TOKEN", "")
    monkeypatch.setattr(replier, "_ai_flags", lambda o, r: [])
    with pytest.raises(PermissionError):
        replier.send("https://github.com/o/r/pull/1", [{"id": 1, "source": "issue", "reply": "hi"}])


def test_send_appends_disclosure_and_records(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AUTO_POST_REPLIES", True)
    monkeypatch.setattr(config, "GITHUB_TOKEN", "t")
    monkeypatch.setattr(replier, "STATE", tmp_path / "r.json")
    monkeypatch.setattr(replier, "_ai_flags", lambda o, r: [])
    posted = []
    monkeypatch.setattr(replier.github, "post", lambda path, body, token=None: posted.append((path, body)))
    replier.send("https://github.com/o/r/pull/1",
                 [{"id": 5, "source": "review", "reply": "Fixed."}, {"id": 6, "source": "issue", "reply": ""}])
    assert len(posted) == 1 and posted[0][0].endswith("/pulls/1/comments/5/replies")
    assert config.AI_DISCLOSURE in posted[0][1]["body"]
    assert json.loads((tmp_path / "r.json").read_text())["o/r#1"]["handled"] == [5]


# ---- github failure must never look like "no policy found"
def test_rate_limit_is_not_silently_clear(monkeypatch):
    import httpx
    from backend import github

    def boom(path, params=None, token=None):
        req = httpx.Request("GET", "https://api.github.com/x")
        raise httpx.HTTPStatusError("rate limit", request=req, response=httpx.Response(403, request=req))

    monkeypatch.setattr(github, "get", boom)
    with pytest.raises(httpx.HTTPStatusError):
        github.raw_file("o", "r", "CONTRIBUTING.md")
    with pytest.raises(httpx.HTTPStatusError):
        github.search_free_issues("org:o", 0)


def test_missing_file_is_none(monkeypatch):
    import httpx
    from backend import github

    def nf(path, params=None, token=None):
        req = httpx.Request("GET", "https://api.github.com/x")
        raise httpx.HTTPStatusError("nf", request=req, response=httpx.Response(404, request=req))

    monkeypatch.setattr(github, "get", nf)
    assert github.raw_file("o", "r", "AI_POLICY.md") is None


# ---- multi-user auth
def _hosted(monkeypatch):
    from backend import auth
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "id")
    monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "secret")
    monkeypatch.setattr(config, "BASE_URL", "http://testserver")
    auth.SESSIONS.clear()
    auth.SESSIONS["sidA"] = auth.User(login="alice", token="tokA")
    auth.SESSIONS["sidB"] = auth.User(login="bob", token="tokB")
    from fastapi.testclient import TestClient
    from backend.app import app
    return TestClient(app), auth


MATCH = {"languages": ["Python"], "interests": ["web"]}


def test_hosted_requires_login(monkeypatch):
    c, _ = _hosted(monkeypatch)
    assert c.post("/api/match", json=MATCH).status_code == 401
    assert c.get("/api/usage").status_code == 401
    assert c.get("/api/health").status_code == 200  # public


def test_hosted_logged_in_ok(monkeypatch):
    c, _ = _hosted(monkeypatch)
    r = c.post("/api/match", json=MATCH, cookies={"oss_session": "sidA"})
    assert r.status_code == 200 and r.json()["ranking"]
    assert c.get("/api/me", cookies={"oss_session": "sidA"}).json()["login"] == "alice"


def test_cross_origin_post_blocked(monkeypatch):
    c, _ = _hosted(monkeypatch)
    r = c.post("/api/match", json=MATCH, cookies={"oss_session": "sidA"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_usage_is_per_user(monkeypatch):
    c, _ = _hosted(monkeypatch)
    monkeypatch.setattr(llm, "ledger", llm.Ledger())
    llm.ledger.session("alice").cost_usd = 0.2
    a = c.get("/api/usage", cookies={"oss_session": "sidA"}).json()["session"]["cost_usd"]
    b = c.get("/api/usage", cookies={"oss_session": "sidB"}).json()["session"]["cost_usd"]
    assert (a, b) == (0.2, 0)


def test_cannot_draft_for_someone_elses_pr(monkeypatch):
    _hosted(monkeypatch)
    monkeypatch.setattr(replier.github, "get", lambda path, params=None, token=None: {"user": {"login": "carol"}, "title": "t"})
    with pytest.raises(PermissionError):
        replier.fetch_new_comments("o", "r", 1, "alice")


def test_github_cache_not_shared_between_tokens(monkeypatch):
    import httpx
    from backend import auth, github
    github._cache.clear()
    calls = []

    class R:
        def __init__(self, tok): self.tok = tok
        def raise_for_status(self): pass
        def json(self): return {"seen_by": self.tok}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(headers.get("Authorization"))
        return R(headers.get("Authorization"))

    monkeypatch.setattr(httpx, "get", fake_get)
    auth.current_token.set("tokA"); a = github.get("/repos/o/private")
    auth.current_token.set("tokB"); b = github.get("/repos/o/private")
    assert a != b and len(calls) == 2


def test_hosted_never_uses_operator_gh_login(monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "x")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "x")
    assert config._github_token() == ""


def test_token_reaches_endpoint_thread(monkeypatch):
    c, auth = _hosted(monkeypatch)
    from backend import agents
    seen = {}
    monkeypatch.setattr(agents, "scout", lambda org, profile, sid, repo=None, fallbacks=None: seen.update(tok=auth.current_token.get(), sid=sid) or {"picks": []})
    r = c.post("/api/scout", json={"org": "zulip", "profile": {}}, cookies={"oss_session": "sidB"})
    assert r.status_code == 200 and seen == {"tok": "tokB", "sid": "bob"}


def test_orgs_endpoint_is_public_and_minimal(monkeypatch):
    c, _ = _hosted(monkeypatch)
    r = c.get("/api/orgs")  # no login: the 3D galaxy must render before sign-in
    assert r.status_code == 200 and len(r.json()) >= 10
    assert set(r.json()[0]) == {"name", "github", "languages", "domains", "beginner", "notes"}


def test_catalogue_is_large_and_well_formed():
    cat = matcher.catalogue()
    assert len(cat) >= 100
    names = [o["name"] for o in cat]
    logins = [o["github"].lower() for o in cat]
    assert len(set(names)) == len(names) and len(set(logins)) == len(logins)
    for o in cat:
        assert o["languages"] and o["domains"] and o["setup"] in ("light", "medium", "heavy")
        assert 1 <= o["beginner"] <= 5 and 1 <= o["hackathon"] <= 5


def test_every_quiz_interest_and_language_has_orgs():
    from backend.app import QUESTIONS
    cat = matcher.catalogue()
    for q in QUESTIONS:
        if q["id"] == "interests":
            for v, _ in q["options"]:
                assert any(v in o["domains"] for o in cat), v
        if q["id"] == "languages":
            for v, _ in q["options"]:
                assert any(v in o["languages"] for o in cat), v


def test_rank_all_returns_runner_ups_without_gated(monkeypatch):
    top, others = matcher.rank_all({**PROFILE, "legal": "dco"})
    assert len(top) == 3 and 1 <= len(others) <= 12
    assert all(not o["gate"] for o in others) and not {t["org"] for t in top} & {o["org"] for o in others}


def test_discover_dedupes_known_and_one_per_owner(monkeypatch):
    from backend import github
    def item(full, stars, owner=None):
        o = owner or full.split("/")[0]
        return {"full_name": full, "owner": {"login": o}, "stargazers_count": stars, "description": "d", "language": "Python",
                "pushed_at": "2026-09-01T00:00:00Z", "topics": [], "license": None, "html_url": "u", "open_issues_count": 5}
    queries = []
    def fake_get(path, params=None, token=None):
        queries.append(params["q"])
        return {"items": [item("zulip/zulip", 99999), item("a/x", 500), item("a/y", 900), item("b/z", 700)]}
    monkeypatch.setattr(github, "get", fake_get)
    out = github.discover(["Python"], ["web"], known={"zulip"})
    assert [r["repo"] for r in out] == ["a/y", "b/z"]          # known org removed, one repo per owner, by stars
    assert "good-first-issues:>3" in queries[0] and "language:Python" in queries[0] and "topic:web" in queries[0]
    assert "archived:false" in queries[0]


def test_discover_endpoint_requires_login_when_hosted(monkeypatch):
    c, _ = _hosted(monkeypatch)
    assert c.get("/api/discover?languages=Python").status_code == 401


# ---- scouting: widening, fallback, claims, verify
def _issue(repo, n, comments=1):
    return {"number": n, "title": f"t{n}", "url": "u", "repo": repo, "labels": [], "comments": comments, "updated": "2026-10-01T00:00:00Z", "body": ""}


def _stub_scout(monkeypatch, per_scope, claims=(), prs=()):
    from backend import agents, github
    calls = []

    def search(scope, tier, limit=40):
        calls.append((scope, tier))
        items = per_scope.get((scope, tier), [])
        return items, len(items)

    monkeypatch.setattr(github, "search_free_issues", search)
    monkeypatch.setattr(github, "policy_scan", lambda o, r: {"files": [], "ai_flags": [], "legal": []})
    monkeypatch.setattr(github, "verify_issue", lambda o, r, n, light=False: (
        {"ok": False, "reason": "someone said they are working on it", "checked_at": "t"} if (r, n) in claims
        else {"ok": False, "reason": "an open pull request already references it (#9)", "checked_at": "t"} if (r, n) in prs
        else {"ok": True, "reason": "", "checked_at": "2026-10-07T00:00:00+00:00"}))

    def fake_ask(**kw):
        import json as _j
        cand = _j.loads(kw["messages"][0]["content"])["candidates"]
        return {"text": _j.dumps({"picks": [{"repo": c["repo"], "number": c["number"], "fit": "f", "learn": "l", "hours": 2, "risk": "r"} for c in cand[:3]]}), "cost_usd": 0.001}

    monkeypatch.setattr(agents.llm, "ask", fake_ask)
    return agents, calls


def test_scout_widens_labels_before_giving_up(monkeypatch):
    agents, calls = _stub_scout(monkeypatch, {("user:acme", 1): [_issue("acme/x", 5)]})
    res = agents.scout("acme", {"mode": "learn"}, "s")
    assert [c[1] for c in calls] == [0, 1] and res["picks"] and res["org_used"] == "acme"


def test_scout_falls_back_to_next_org_instead_of_dead_end(monkeypatch):
    agents, calls = _stub_scout(monkeypatch, {("user:beta", 0): [_issue("beta/y", 9)]})
    events = list(agents.scout_stream("alpha", {"mode": "learn"}, "s", fallbacks=["beta", "gamma"]))
    res = events[-1]
    assert res["org_used"] == "beta" and res["picks"][0]["repo"] == "beta/y"
    assert any("Nothing open and unclaimed in alpha" in e.get("text", "") for e in events)
    assert res["stats"]["tried"] == ["alpha", "beta"]


def test_scout_drops_claimed_issues_and_says_so(monkeypatch):
    agents, _ = _stub_scout(monkeypatch, {("user:acme", 0): [_issue("acme/x", 1), _issue("acme/x", 2)]}, claims={("x", 1)})
    res = agents.scout("acme", {"mode": "learn"}, "s")
    assert [p["number"] for p in res["picks"]] == [2] and res["stats"]["claimed"] == 1


def test_scout_empty_everywhere_reports_stats_not_exception(monkeypatch):
    agents, _ = _stub_scout(monkeypatch, {})
    res = agents.scout("a", {"mode": "learn"}, "s", fallbacks=["b", "c", "d"])
    assert res["picks"] == [] and res["stats"]["tried"] == ["a", "b", "c"]  # capped at three attempts


def test_scout_makes_one_search_per_tier_not_one_per_issue(monkeypatch):
    agents, calls = _stub_scout(monkeypatch, {("user:acme", 0): [_issue("acme/x", n) for n in range(1, 30)]})
    agents.scout("acme", {"mode": "learn"}, "s")
    assert len(calls) == 1  # the old design made a search per issue and hit GitHub's 30/min limit


def test_claim_regex():
    from backend.github import CLAIM_RE
    for t in ["I'll take this", "Can I work on this?", "working on it", "please assign this to me", "I would like to work on this"]:
        assert CLAIM_RE.search(t), t
    for t in ["Thanks for the report", "this also breaks on windows", "see #123"]:
        assert not CLAIM_RE.search(t), t


def test_verify_issue_reports_reason(monkeypatch):
    from backend import github
    monkeypatch.setattr(github, "recent_claim", lambda *a: False)
    def fake_get(path, params=None, token=None):
        if path.endswith("/timeline"):
            return [{"event": "cross-referenced", "source": {"issue": {"number": 77, "state": "open", "pull_request": {}}}}]
        return {"state": "open", "assignees": []}
    monkeypatch.setattr(github, "get", fake_get)
    r = github.verify_issue("o", "r", 1)
    assert r["ok"] is False and "#77" in r["reason"] and r["linked_prs"] == [77]
    monkeypatch.setattr(github, "get", lambda path, params=None, token=None: [] if path.endswith("/timeline") else {"state": "open", "assignees": []})
    assert github.verify_issue("o", "r", 1)["ok"] is True


def test_scout_stream_endpoint_emits_ndjson(monkeypatch):
    c, _ = _hosted(monkeypatch)
    from backend import agents
    monkeypatch.setattr(agents, "scout_stream", lambda *a, **k: iter([{"type": "step", "text": "hi"}, {"type": "result", "picks": []}]))
    r = c.post("/api/scout/stream", json={"org": "x", "profile": {}}, cookies={"oss_session": "sidA"})
    lines = [json.loads(l) for l in r.text.strip().splitlines()]
    assert r.status_code == 200 and lines[0]["type"] == "step" and lines[-1]["type"] == "result"


def test_scout_drops_issues_with_open_prs_and_counts_them(monkeypatch):
    agents, _ = _stub_scout(monkeypatch, {("user:acme", 0): [_issue("acme/x", 1), _issue("acme/x", 2), _issue("acme/x", 3)]}, claims={("x", 1)}, prs={("x", 2)})
    res = agents.scout("acme", {"mode": "learn"}, "s")
    assert [p["number"] for p in res["picks"]] == [3]
    assert res["stats"]["claimed"] == 1 and res["stats"]["has_pr"] == 1 and res["picks"][0]["verified_at"].startswith("2026-10-07")
