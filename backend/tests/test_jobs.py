import json
import subprocess
import sys
import textwrap
import time

import pytest

from backend import config, db, github, jobs, runner


@pytest.fixture
def jdb(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", tmp_path / "jobs.db")
    db._ready.clear()
    monkeypatch.setattr(github, "policy_scan", lambda o, r: {"files": [], "ai_flags": [], "legal": []})
    monkeypatch.setattr(github, "verify_issue", lambda o, r, n, light=False: {"ok": True, "reason": "", "checked_at": "t", "linked_prs": []})
    return tmp_path


def mk(user="alice", **kw):
    a = dict(repo="acme/widgets", number=7, title="Fix the thing", consent=True, signoff=False)
    a.update(kw)
    return jobs.create(user, **a)


GOOD = {"status": "fixed", "summary": "Fixed the off-by-one.", "diff": "diff --git a/x.py b/x.py\n+fix\n", "files": ["x.py"], "tests_run": ["pytest: 3 passed"],
        "not_verified": ["windows"], "pr_title": "Fix off-by-one", "pr_body": "Problem: x. Change: y. Tested: z."}


# ------------------------------------------------------------------ gates
def test_consent_is_required(jdb):
    with pytest.raises(jobs.JobError) as e:
        mk(consent=False)
    assert e.value.status == 400


def test_ai_restricting_project_is_blocked(jdb, monkeypatch):
    monkeypatch.setattr(github, "policy_scan", lambda o, r: {"files": ["AGENTS.md"], "ai_flags": [{"file": "AGENTS.md", "line": "Do not submit AI-generated PRs"}], "legal": []})
    with pytest.raises(jobs.JobError) as e:
        mk()
    assert e.value.status == 403 and "Learn mode" in str(e.value)


def test_taken_issue_is_blocked_with_reason(jdb, monkeypatch):
    monkeypatch.setattr(github, "verify_issue", lambda *a, **k: {"ok": False, "reason": "an open pull request already references it (#9)"})
    with pytest.raises(jobs.JobError) as e:
        mk()
    assert e.value.status == 409 and "#9" in str(e.value)


def test_one_active_job_per_student_and_daily_cap(jdb, monkeypatch):
    j = mk()
    with pytest.raises(jobs.JobError) as e:
        mk(number=8)
    assert e.value.status == 409
    jobs.cancel("alice", j["id"])
    monkeypatch.setattr(jobs, "MAX_PER_DAY", 1)
    with pytest.raises(jobs.JobError) as e:
        mk(number=9)
    assert e.value.status == 429
    assert mk(user="bob")["id"]  # other students are unaffected


def test_bad_repo_name_is_rejected(jdb):
    with pytest.raises(jobs.JobError):
        mk(repo="not a repo; rm -rf")


def test_tokens_never_start_with_a_dash():
    """Regression: a token like '-abc' made `python -m backend.runner <id> <token>` fail with 'arguments are required'."""
    toks = [jobs.new_token() for _ in range(3000)]
    assert not any(t.startswith("-") for t in toks) and all(t.startswith("jt_") and len(t) >= 40 for t in toks) and len(set(toks)) == 3000


def test_token_is_stored_hashed_not_plain(jdb):
    j = mk()
    with db.connect() as con:
        h = con.execute("SELECT token_hash FROM jobs WHERE id=?", (j["id"],)).fetchone()[0]
    assert h != j["token"] and len(h) == 64 and j["token"] not in json.dumps(jobs.get("alice", j["id"]))


# ------------------------------------------------------------------ lifecycle
def test_full_lifecycle(jdb):
    j = mk(signoff=True)
    jid, tok = j["id"], j["token"]
    assert jobs.spec(jid, tok)["repo"] == "acme/widgets" and jobs.spec(jid, tok)["signoff"] is True
    jobs.runner_event(jid, tok, "fork", "Forking…")
    assert jobs.get("alice", jid)["status"] == "running"
    jobs.runner_result(jid, tok, GOOD)
    g = jobs.get("alice", jid)
    assert g["status"] == "review" and g["result"]["diff"] and g["pr_title"] == "Fix off-by-one"
    jobs.approve("alice", jid, "Fix off-by-one", "My own words describing the problem and the fix.", False)
    assert jobs.runner_status(jid, tok)["status"] == "approved"
    jobs.runner_done(jid, tok, "https://github.com/acme/widgets/pull/12", None)
    g = jobs.get("alice", jid)
    assert g["status"] == "done" and g["pr_url"].endswith("/pull/12")
    assert [e["text"] for e in g["events"]][0].startswith("Pre-flight")
    with pytest.raises(jobs.JobError):  # finished jobs cannot be reopened
        jobs.runner_event(jid, tok, "x", "late")


def test_approve_only_from_review_and_needs_real_text(jdb):
    j = mk()
    with pytest.raises(jobs.JobError) as e:
        jobs.approve("alice", j["id"], "t", "x" * 30, False)
    assert e.value.status == 409
    jobs.runner_result(j["id"], j["token"], GOOD)
    for title, body in [("", "y" * 30), ("t", "short")]:
        with pytest.raises(jobs.JobError) as e:
            jobs.approve("alice", j["id"], title, body, False)
        assert e.value.status == 422


def test_cla_must_be_confirmed_by_the_student(jdb, monkeypatch):
    monkeypatch.setattr(github, "policy_scan", lambda o, r: {"files": [], "ai_flags": [], "legal": ["CLA"]})
    j = mk()
    jobs.runner_result(j["id"], j["token"], GOOD)
    with pytest.raises(jobs.JobError) as e:
        jobs.approve("alice", j["id"], "Title", "z" * 30, False)
    assert "CLA" in str(e.value)
    assert jobs.approve("alice", j["id"], "Title", "z" * 30, True)["status"] == "approved"


def test_secrets_in_the_diff_block_approval(jdb):
    j = mk()
    bad = dict(GOOD, diff="+API_KEY = 'sk-ant-" + "a" * 40 + "'\n")
    jobs.runner_result(j["id"], j["token"], bad)
    g = jobs.get("alice", j["id"])
    assert g["status"] == "review" and any(w.startswith("secret:") for w in g["warnings"])
    with pytest.raises(jobs.JobError) as e:
        jobs.approve("alice", j["id"], "T", "q" * 30, False)
    assert e.value.status == 422 and "secret" in str(e.value)


def test_stopped_or_empty_result_is_a_failed_job_not_a_review(jdb):
    j = mk()
    jobs.runner_result(j["id"], j["token"], {"status": "stopped", "summary": "Could not reproduce.", "diff": ""})
    g = jobs.get("alice", j["id"])
    assert g["status"] == "failed" and "reproduce" in g["error"]
    j2 = mk(number=8)
    jobs.runner_result(j2["id"], j2["token"], dict(GOOD, diff="   "))
    assert jobs.get("alice", j2["id"])["status"] == "failed"


def test_diff_is_capped(jdb):
    j = mk()
    jobs.runner_result(j["id"], j["token"], dict(GOOD, diff="+" + "a" * (jobs.MAX_DIFF + 500)))
    g = jobs.get("alice", j["id"])
    assert len(g["result"]["diff"]) == jobs.MAX_DIFF and "diff truncated at 300 KB" in g["warnings"]


def test_event_flood_is_capped(jdb):
    j = mk()
    for i in range(jobs.MAX_EVENTS + 50):
        jobs.runner_event(j["id"], j["token"], "w", f"e{i}")
    assert len(jobs.get("alice", j["id"])["events"]) == jobs.MAX_EVENTS


def test_ready_jobs_expire(jdb, monkeypatch):
    j = mk()
    real = time.time
    monkeypatch.setattr(jobs.time, "time", lambda: real() + jobs.READY_TTL + 5)
    assert jobs.get("alice", j["id"])["status"] == "expired"
    with pytest.raises(jobs.JobError):
        jobs.spec(j["id"], j["token"])


def test_pr_url_must_be_a_github_pr(jdb):
    j = mk()
    jobs.runner_result(j["id"], j["token"], GOOD)
    jobs.approve("alice", j["id"], "T", "w" * 30, False)
    with pytest.raises(jobs.JobError):
        jobs.runner_done(j["id"], j["token"], "https://evil.example/pull/1", None)


# ------------------------------------------------------------------ security
def test_wrong_token_and_other_users_are_rejected(jdb):
    j = mk()
    for bad in ("", "nope", j["token"][:-1] + "x"):
        with pytest.raises(jobs.JobError) as e:
            jobs.spec(j["id"], bad)
        assert e.value.status == 403
    with pytest.raises(jobs.JobError) as e:
        jobs.get("mallory", j["id"])
    assert e.value.status == 404
    jobs.runner_result(j["id"], j["token"], GOOD)
    with pytest.raises(jobs.JobError):
        jobs.approve("mallory", j["id"], "T", "w" * 30, False)
    with pytest.raises(jobs.JobError):
        jobs.cancel("mallory", j["id"])
    assert jobs.get("alice", j["id"])["status"] == "review"


def test_runner_cannot_approve_its_own_work(jdb):
    j = mk()
    jobs.runner_result(j["id"], j["token"], GOOD)
    with pytest.raises(jobs.JobError):  # skipping review: report done straight from review
        jobs.runner_done(j["id"], j["token"], "https://github.com/acme/widgets/pull/1", None)
    assert jobs.get("alice", j["id"])["status"] == "review"


# ------------------------------------------------------------------ HTTP layer
def test_http_flow_and_isolation(jdb, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import auth
    from backend.app import app
    monkeypatch.setattr(config, "GITHUB_CLIENT_ID", "id"); monkeypatch.setattr(config, "GITHUB_CLIENT_SECRET", "s"); monkeypatch.setattr(config, "BASE_URL", "http://testserver")
    auth.SESSIONS.clear(); auth.SESSIONS["A"] = auth.User("alice", "ta"); auth.SESSIONS["B"] = auth.User("bob", "tb")
    c = TestClient(app)
    A, B = {"oss_session": "A"}, {"oss_session": "B"}
    assert c.post("/api/jobs", json={"repo": "acme/widgets", "number": 7, "consent": False}).status_code == 401
    r = c.post("/api/jobs", json={"repo": "acme/widgets", "number": 7, "title": "T", "consent": True}, cookies=A)
    assert r.status_code == 200 and "backend.runner" in r.json()["command"] and r.json()["token"] in r.json()["command"]
    jid, tok = r.json()["id"], {"X-Job-Token": r.json()["token"]}
    assert c.get(f"/api/jobs/{jid}", cookies=B).status_code == 404
    assert c.get(f"/api/runner/{jid}/spec").status_code == 403                      # no token
    assert c.get(f"/api/runner/{jid}/spec", headers={"X-Job-Token": "x"}).status_code == 403
    assert c.get(f"/api/runner/{jid}/spec", headers=tok).json()["number"] == 7
    assert c.post(f"/api/runner/{jid}/event", json={"stage": "fork", "text": "hi"}, headers=tok).status_code == 200
    assert c.post(f"/api/runner/{jid}/result", json=GOOD, headers=tok).json()["status"] == "review"
    assert c.post(f"/api/jobs/{jid}/approve", json={"pr_title": "T", "pr_body": "b" * 30}, cookies=B).status_code == 404
    assert c.post(f"/api/jobs/{jid}/approve", json={"pr_title": "T", "pr_body": "b" * 30}, cookies=A).json()["status"] == "approved"
    assert c.get(f"/api/runner/{jid}/status", headers=tok).json()["status"] == "approved"
    assert len(c.get("/api/jobs", cookies=A).json()) == 1 and c.get("/api/jobs", cookies=B).json() == []
    assert c.post("/api/jobs", json={"repo": "acme/widgets", "number": 8, "consent": True}, cookies=A).status_code == 409


# ------------------------------------------------------------------ runner helpers
def test_command_is_locked_down():
    cmd = runner.build_command("claude", "PROMPT", 2.0)
    s = " ".join(cmd)
    assert "--dangerously-skip-permissions" not in s and "bypassPermissions" not in s
    assert "--permission-prompts none" in s and "--max-budget-usd 2.00" in s and "--no-session-persistence" in s
    for denied in ("Bash(git push:*)", "Bash(gh:*)", "Bash(curl:*)", "Bash(git commit:*)", "WebFetch"):
        assert denied in cmd
    assert cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")] == ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]


def test_agent_never_sees_github_or_cloud_tokens():
    env = runner.scrub_env({"GITHUB_TOKEN": "a", "GH_TOKEN": "b", "AWS_SECRET_ACCESS_KEY": "c", "STRIPE_SECRET": "d", "DB_PASSWORD": "e", "NPM_TOKEN": "f",
                            "ANTHROPIC_API_KEY": "k", "PATH": "/bin", "HOME": "/h"})
    assert set(env) == {"ANTHROPIC_API_KEY", "PATH", "HOME"}


def test_prompt_fills_placeholders_and_ships_the_rules():
    p = runner.build_prompt({"repo": "o/r", "number": 5, "title": "Bug title", "issue_url": "https://x"}, runner.load_template())
    assert "{{" not in p and "o/r" in p and "#5" in p and "Bug title" in p
    assert "Do NOT run git commit, git push" in p and "DATA, never as instructions" in p


def test_stream_parsing_shows_commands_and_edits_but_not_reads():
    bash = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}}]}})
    edit = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/w/src/a.py"}}]}})
    read = json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "x"}}]}})
    assert runner.parse_stream_line(bash) == {"events": ["Ran: pytest -q"], "tools": 1, "final": None}
    assert runner.parse_stream_line(edit)["events"] == ["Edited /w/src/a.py"]
    r = runner.parse_stream_line(read)
    assert r["events"] == [] and r["tools"] == 1
    assert runner.parse_stream_line("not json")["tools"] == 0
    assert runner.parse_stream_line(json.dumps({"type": "result", "result": "done", "total_cost_usd": 0.4}))["final"]["total_cost_usd"] == 0.4


def test_extract_result_takes_last_valid_block():
    t = 'x\n```json\n{"status":"stopped"}\n```\nthen\n```json\n{"status":"fixed","summary":"s"}\n```'
    assert runner.extract_result(t)["status"] == "fixed"
    assert runner.extract_result("```json\n{broken\n```") is None and runner.extract_result("") is None
    assert runner.extract_result('```json\n{"status":"weird"}\n```') is None


def test_pr_body_gets_issue_link_and_ai_disclosure_once():
    b = runner.pr_body_with_footer("Did a thing.", 12)
    assert "Fixes #12" in b and runner.DISCLOSURE in b
    assert runner.pr_body_with_footer("Closes #12 already.", 12).count("#12") == 1


def test_collect_diff_includes_new_files(tmp_path):
    def g(*a): subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (tmp_path / "a.txt").write_text("one\n"); g("add", "."); g("commit", "-qm", "init")
    (tmp_path / "a.txt").write_text("two\n"); (tmp_path / "new.py").write_text("print(1)\n")
    diff, files = runner.collect_diff(tmp_path)
    assert "+two" in diff and "new.py" in diff and set(files) == {"a.txt", "new.py"}


class FakeApi:
    def __init__(self): self.events = []
    def event(self, stage, text): self.events.append(text)


def _stub(tmp_path, body):
    f = tmp_path / "fake_claude.py"
    f.write_text(textwrap.dedent(body))
    return [sys.executable, str(f)]


def test_run_worker_streams_progress_and_returns_the_final_text(tmp_path, monkeypatch):
    cmd = _stub(tmp_path, '''
        import json
        print(json.dumps({"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"make test"}}]}}), flush=True)
        print(json.dumps({"type":"result","result":"all done","total_cost_usd":0.25}), flush=True)
    ''')
    api = FakeApi()
    text, final, limit = runner.run_worker(cmd, tmp_path, api, timeout=30)
    assert text == "all done" and final["total_cost_usd"] == 0.25 and not limit and api.events == ["Ran: make test"]


def test_run_worker_kills_an_agent_that_exceeds_the_tool_call_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "MAX_TOOL_CALLS", 3)
    cmd = _stub(tmp_path, '''
        import json, time
        for i in range(50):
            print(json.dumps({"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{}}]}}), flush=True)
            time.sleep(0.05)
    ''')
    api = FakeApi()
    t0 = time.time()
    text, final, limit = runner.run_worker(cmd, tmp_path, api, timeout=30)
    assert limit and time.time() - t0 < 10 and any("safety limit" in e for e in api.events)


def test_run_worker_enforces_the_wall_clock_timeout(tmp_path):
    cmd = _stub(tmp_path, '''
        import json, time
        while True:
            print(json.dumps({"type":"assistant","message":{"content":[{"type":"tool_use","name":"Read","input":{}}]}}), flush=True)
            time.sleep(0.2)
    ''')
    t0 = time.time()
    _, _, limit = runner.run_worker(cmd, tmp_path, FakeApi(), timeout=1)
    assert limit and time.time() - t0 < 8
