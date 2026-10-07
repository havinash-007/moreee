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
    assert top[0]["org"] in ("Zulip", "Oppia", "Home Assistant")
    assert all(0 <= t["total"] <= 55 for t in top)


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
        github.candidate_issues("o", "r")


def test_missing_file_is_none(monkeypatch):
    import httpx
    from backend import github

    def nf(path, params=None, token=None):
        req = httpx.Request("GET", "https://api.github.com/x")
        raise httpx.HTTPStatusError("nf", request=req, response=httpx.Response(404, request=req))

    monkeypatch.setattr(github, "get", nf)
    assert github.raw_file("o", "r", "AI_POLICY.md") is None
