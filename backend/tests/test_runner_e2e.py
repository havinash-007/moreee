"""Whole-runner test, fully offline: a real local server, fake `gh` and `claude` programs, and local bare git repos standing in for
GitHub. Proves the runner forks, branches, runs the agent in the right directory WITHOUT GitHub tokens, uploads the diff, waits for
approval, then commits (with DCO sign-off), pushes to the fork and opens the PR with the right arguments."""
import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time

import httpx
import pytest
import uvicorn

from backend import db, github


def git(*a, cwd=None, env=None):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


@pytest.fixture
def world(tmp_path, monkeypatch):
    py = sys.executable
    # --- GitHub stand-ins: upstream (the project), fork (the student's copy)
    seed = tmp_path / "seed"; seed.mkdir()
    git("init", "-q", "-b", "main", cwd=seed); git("config", "user.email", "m@x", cwd=seed); git("config", "user.name", "Maintainer", cwd=seed)
    (seed / "src").mkdir(); (seed / "src" / "parser.py").write_text("def parse(items):\n    return [items[i] for i in range(len(items) - 1)]\n")
    git("add", ".", cwd=seed); git("commit", "-qm", "init", cwd=seed)
    upstream, fork = tmp_path / "upstream.git", tmp_path / "fork.git"
    git("clone", "-q", "--bare", str(seed), str(upstream)); git("clone", "-q", "--bare", str(upstream), str(fork))
    # --- fake executables first on PATH
    bin_ = tmp_path / "bin"; bin_.mkdir()
    log = tmp_path / "calls.json"
    def stub(name, code):
        f = bin_ / name; f.write_text(f"#!{py}\n" + textwrap.dedent(code)); f.chmod(0o755)
    stub("gh", f'''
        import json, os, subprocess, sys
        a = sys.argv[1:]; LOG = {str(log)!r}
        def rec(k, v):
            d = json.load(open(LOG)) if os.path.exists(LOG) else {{}}
            d[k] = v; json.dump(d, open(LOG, "w"))
        if a[:2] == ["auth", "status"]: sys.exit(0)
        if a[:2] == ["api", "user"]: print("student")
        elif a[:2] == ["repo", "fork"]:
            # strict like the real gh: --remote is invalid with a repository argument; --clone=false must be explicit to avoid a prompt
            if "--remote" in a: print("the `--remote` flag is unsupported when a repository argument is provided", file=sys.stderr); sys.exit(1)
            if "--clone=false" not in a: print("would prompt: Would you like to clone the fork?", file=sys.stderr); sys.exit(1)
            rec("forked", a[2]); rec("fork_name", a[a.index("--fork-name") + 1] if "--fork-name" in a else "")
            if a[2] == "acme/widgets": open(LOG + ".made", "a").write((a[a.index("--fork-name") + 1] if "--fork-name" in a else "widgets") + "\\n")
        elif a[:2] == ["repo", "view"] and "parent" in " ".join(a):
            made = open(LOG + ".made").read().split() if os.path.exists(LOG + ".made") else []
            n = a[2].split("/")[1]
            # real gh's `parent` object has no nameWithOwner (only id, name, owner.login), so that jq path prints nothing
            print("acme/widgets" if "nameWithOwner" not in " ".join(a) and a[2].startswith("student/") and (n in made or os.environ.get("FAKE_GH_PREFORKED")) else "")
        elif a[:2] == ["repo", "view"] and "name" in " ".join(a):
            print(a[2].split("/")[1] if a[2] in os.environ.get("FAKE_GH_TAKEN", "").split(",") else "")
        elif a[:2] == ["repo", "view"]: print("main")
        elif a[:2] == ["repo", "clone"]:
            name = a[2].split("/")[1]
            subprocess.run(["git", "clone", "-q", {str(fork)!r}, name], check=True)
            if os.environ.get("FAKE_GH_ADDS_UPSTREAM"):                # real gh adds `upstream` when cloning a fork
                subprocess.run(["git", "remote", "add", "upstream", {str(upstream)!r}], cwd=name, check=True)
        elif a[:2] == ["pr", "create"]:
            body = open(a[a.index("--body-file") + 1]).read()
            rec("pr", {{"args": a, "body": body}}); print("https://github.com/acme/widgets/pull/77")
        else: sys.exit(3)
    ''')
    stub("claude", f'''
        import json, os, sys
        d = json.load(open({str(log)!r})) if os.path.exists({str(log)!r}) else {{}}
        d["claude"] = {{"args": sys.argv[1:], "cwd": os.getcwd(), "has_github_token": "GITHUB_TOKEN" in os.environ or "GH_TOKEN" in os.environ}}
        json.dump(d, open({str(log)!r}, "w"))
        p = "src/parser.py"; s = open(p).read().replace("len(items) - 1", "len(items)"); open(p, "w").write(s)
        os.makedirs("tests", exist_ok=True); open("tests/test_parser.py", "w").write("from src.parser import parse\\ndef test_all():\\n    assert parse([1, 2]) == [1, 2]\\n")
        print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "tool_use", "name": "Bash", "input": {{"command": "pytest -q"}}}}]}}}}), flush=True)
        res = {{"status": "fixed", "summary": "Loop bound was off by one.", "files": ["src/parser.py"], "tests_run": ["pytest: 1 passed"], "not_verified": [],
                "pr_title": "Fix parse() dropping the last item", "pr_body": "Problem: dropped the last item. Change: loop bound. Tested: pytest."}}
        print(json.dumps({{"type": "result", "result": "Done.\\n```json\\n" + json.dumps(res) + "\\n```", "total_cost_usd": 0.12}}), flush=True)
    ''')
    gitcfg = tmp_path / "gitconfig"; gitcfg.write_text("[user]\n\tname = Real Student\n\temail = student@example.com\n")
    # --- real local server with an isolated DB and stubbed GitHub reads
    monkeypatch.setattr(db, "PATH", tmp_path / "jobs.db"); db._ready.clear()
    monkeypatch.setattr(github, "policy_scan", lambda o, r: {"files": [], "ai_flags": [], "legal": ["DCO"]})
    monkeypatch.setattr(github, "verify_issue", lambda o, r, n, light=False: {"ok": True, "reason": "", "checked_at": "t", "linked_prs": []})
    from backend.app import app
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True); t.start()
    for _ in range(100):
        try: httpx.get(f"http://127.0.0.1:{port}/api/health"); break
        except httpx.HTTPError: time.sleep(0.1)
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", GITHUB_TOKEN="leak-me", GH_TOKEN="leak-me-too", FAKE_GH_ADDS_UPSTREAM="1", GIT_CONFIG_GLOBAL=str(gitcfg), GIT_CONFIG_NOSYSTEM="1")
    yield {"base": f"http://127.0.0.1:{port}", "env": env, "fork": fork, "log": log, "work": tmp_path / "jobs"}
    srv.should_exit = True; t.join(timeout=5)


def test_runner_end_to_end(world):
    base = world["base"]
    j = httpx.post(base + "/api/jobs", json={"repo": "acme/widgets", "number": 7, "title": "parse() drops the last item", "consent": True, "signoff": True}).json()
    proc = subprocess.Popen([sys.executable, "-m", "backend.runner", j["id"], j["token"], "--server", base, "--workdir", str(world["work"]), "--yes"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=world["env"], cwd=os.getcwd())
    try:
        job = None
        for _ in range(300):  # wait for the review state
            job = httpx.get(f"{base}/api/jobs/{j['id']}").json()
            if job["status"] in ("review", "failed"): break
            time.sleep(0.2)
        assert job["status"] == "review", (job, proc.stdout.read() if proc.poll() is not None else "")
        assert "+    return [items[i] for i in range(len(items))]" in job["result"]["diff"] and "tests/test_parser.py" in job["result"]["diff"]
        assert job["pr_title"] == "Fix parse() dropping the last item" and job["result"]["tests_run"] == ["pytest: 1 passed"]
        assert any("Ran: pytest -q" in e["text"] for e in job["events"]) and any("Forking" in e["text"] for e in job["events"])
        # nothing may have been pushed or opened before approval
        assert "fix/7-oss-mentor" not in git("branch", cwd=world["fork"])
        assert not os.path.exists(world["log"]) or "pr" not in json.load(open(world["log"]))

        r = httpx.post(f"{base}/api/jobs/{j['id']}/approve", json={"pr_title": "Fix parse() dropping the last item", "pr_body": "I fixed an off-by-one in the loop bound and added a regression test."})
        assert r.status_code == 200
        out, _ = proc.communicate(timeout=60)
    finally:
        if proc.poll() is None: proc.kill()
    assert proc.returncode == 0, out
    final = httpx.get(f"{base}/api/jobs/{j['id']}").json()
    assert final["status"] == "done" and final["pr_url"] == "https://github.com/acme/widgets/pull/77"

    calls = json.load(open(world["log"]))
    # the agent ran in the cloned repo, was locked down, and never saw GitHub tokens
    assert calls["claude"]["cwd"].endswith("/widgets") and calls["claude"]["has_github_token"] is False
    cargs = calls["claude"]["args"]
    assert "--permission-prompts" in cargs and "Bash(git push:*)" in cargs and "Bash(gh:*)" in cargs and "--dangerously-skip-permissions" not in cargs
    # the commit landed on the student's fork, on the right branch, signed off with their own identity
    assert "fix/7-oss-mentor" in git("branch", cwd=world["fork"])
    msg = git("log", "-1", "--format=%B", "fix/7-oss-mentor", cwd=world["fork"])
    assert msg.startswith("Fix parse() dropping the last item") and "Signed-off-by: Real Student <student@example.com>" in msg
    # the PR was opened from the student's fork with an honest body
    pr = calls["pr"]; a = pr["args"]
    assert a[a.index("--repo") + 1] == "acme/widgets" and a[a.index("--head") + 1] == "student:fix/7-oss-mentor"
    assert "Fixes #7" in pr["body"] and "AI assistance" in pr["body"] and "off-by-one" in pr["body"]


def test_fork_step_matches_the_real_gh_and_adds_upstream_itself(world, tmp_path):
    """Regression for the first real run: `gh repo fork <repo> --clone --remote` is rejected by real gh. Also covers a gh that
    does NOT add the upstream remote when cloning, and a same-named repo that is not a fork of the project."""
    from backend import runner
    env = dict(world["env"]); env.pop("FAKE_GH_ADDS_UPSTREAM")
    old_path = os.environ["PATH"]; os.environ["PATH"] = env["PATH"]
    try:
        work = tmp_path / "w"; work.mkdir()
        repo_dir, default = runner.prepare_repo({"repo": "acme/widgets", "number": 7}, work, "student", sleep=lambda *_: None)
        assert default == "main" and (repo_dir / ".git").exists()
        assert "upstream" in git("remote", cwd=repo_dir) and "origin" in git("remote", cwd=repo_dir)   # runner added upstream itself
        calls = json.load(open(world["log"]))
        assert calls["forked"] == "acme/widgets"
        assert calls["fork_name"] == ""                                                               # default name when it is free
    finally:
        os.environ["PATH"] = old_path


def test_fork_falls_back_to_owner_suffixed_name_when_the_name_is_taken(world, tmp_path):
    """The user's real failure: student/widgets exists but is not a fork of acme/widgets. Must not touch it; fork as widgets-acme."""
    from backend import runner
    env = dict(world["env"]); old = dict(os.environ); os.environ.update(PATH=env["PATH"], FAKE_GH_TAKEN="student/widgets")
    try:
        work = tmp_path / "w"; work.mkdir()
        repo_dir, _ = runner.prepare_repo({"repo": "acme/widgets", "number": 7}, work, "student", sleep=lambda *_: None)
        assert json.load(open(world["log"]))["fork_name"] == "widgets-acme"
        assert repo_dir.name == "widgets-acme"
        os.remove(str(world["log"]) + ".made")                                                       # forget the fork made above
        os.environ["FAKE_GH_TAKEN"] = "student/widgets,student/widgets-acme"
        with pytest.raises(RuntimeError, match="taken or not ready"):
            runner.prepare_repo({"repo": "acme/widgets", "number": 7}, work, "student", sleep=lambda *_: None)
    finally:
        os.environ.clear(); os.environ.update(old)


def test_errors_are_one_readable_line_not_a_usage_dump(tmp_path):
    from backend import runner
    f = tmp_path / "bad"; f.write_text(f"#!{sys.executable}\nimport sys\nprint('the `--remote` flag is unsupported', file=sys.stderr)\nprint('', file=sys.stderr)\nprint('Usage:  gh repo fork', file=sys.stderr)\nprint('Flags:', file=sys.stderr)\nsys.exit(1)\n"); f.chmod(0o755)
    with pytest.raises(RuntimeError) as e:
        runner.sh([str(f), "repo", "fork"], tmp_path)
    assert "\n" not in str(e.value) and "--remote" in str(e.value) and "Usage" not in str(e.value)


def test_runner_reports_failure_when_agent_makes_no_change(world, tmp_path):
    base = world["base"]
    # an agent that changes nothing and says it stopped
    (tmp_path / "bin" / "claude").write_text(f"#!{sys.executable}\n" + textwrap.dedent('''
        import json
        res = {"status": "stopped", "summary": "Could not reproduce the bug."}
        print(json.dumps({"type": "result", "result": "```json\\n" + json.dumps(res) + "\\n```", "total_cost_usd": 0.05}), flush=True)
    '''))
    j = httpx.post(base + "/api/jobs", json={"repo": "acme/widgets", "number": 7, "title": "t", "consent": True}).json()
    p = subprocess.run([sys.executable, "-m", "backend.runner", j["id"], j["token"], "--server", base, "--workdir", str(world["work"]), "--yes"],
                       capture_output=True, text=True, env=world["env"], timeout=90)
    job = httpx.get(f"{base}/api/jobs/{j['id']}").json()
    assert p.returncode == 0 and job["status"] == "failed" and "reproduce" in job["error"]
    assert "fix/7-oss-mentor" not in git("branch", cwd=world["fork"])


def test_runner_refuses_dco_signoff_without_a_real_git_identity(world, tmp_path):
    base = world["base"]
    (tmp_path / "gitconfig").write_text("")  # no name / email configured
    j = httpx.post(base + "/api/jobs", json={"repo": "acme/widgets", "number": 7, "title": "t", "consent": True, "signoff": True}).json()
    proc = subprocess.Popen([sys.executable, "-m", "backend.runner", j["id"], j["token"], "--server", base, "--workdir", str(world["work"]), "--yes"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=world["env"])
    try:
        for _ in range(300):
            if httpx.get(f"{base}/api/jobs/{j['id']}").json()["status"] == "review": break
            time.sleep(0.2)
        httpx.post(f"{base}/api/jobs/{j['id']}/approve", json={"pr_title": "T", "pr_body": "I wrote this description myself, carefully."})
        out, _ = proc.communicate(timeout=60)
    finally:
        if proc.poll() is None: proc.kill()
    job = httpx.get(f"{base}/api/jobs/{j['id']}").json()
    assert job["status"] == "failed" and "real name and email" in job["error"]
    assert "fix/7-oss-mentor" not in git("branch", cwd=world["fork"])  # nothing was pushed under a made-up identity
