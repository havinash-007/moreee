"""Local Full-auto runner. Runs on the STUDENT'S machine with their own `gh` login and Claude Code.

    cd ~/oss-mentor && .venv/bin/python -m backend.runner <job_id> <token> --server http://localhost:8000

What it does, in order:
  1. fetch the job spec (repo, issue) from the web app
  2. fork + clone the repo into ~/oss-mentor-jobs/<job>/ and branch from the upstream default branch
  3. run Claude Code headless with the worker prompt (agents/worker_prompt.md): reproduce, failing test, smallest fix
     - the agent may edit files and run the project's build/tests; it may NOT commit, push, use gh, or fetch URLs
  4. upload the diff + test report for the student's REVIEW in the browser
  5. wait for the student's approval; ONLY THEN commit, push to the student's fork and open the PR with their own gh login
Safety notes: this runs a stranger's build and test commands on this machine. Use a throwaway VM or container for repos you
do not trust. The runner never gives the agent your GitHub token and caps tool calls, time and spend.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DISCLOSURE = "Prepared with AI assistance (Claude Code) and reviewed by the author."
MAX_TOOL_CALLS = 90
DENY = ["Bash(git push:*)", "Bash(git remote:*)", "Bash(git commit:*)", "Bash(gh:*)", "Bash(curl:*)", "Bash(wget:*)", "Bash(ssh:*)", "Bash(scp:*)",
        "Bash(sudo:*)", "Bash(rm -rf /:*)", "Bash(rm -rf ~:*)", "Bash(env:*)", "Bash(printenv:*)", "WebFetch", "WebSearch"]
SECRET_ENV = ("GITHUB_TOKEN", "GH_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_PAT", "NPM_TOKEN", "PYPI_TOKEN", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID")


# ------------------------------------------------------------------ pure helpers (unit-tested)
def scrub_env(env: dict) -> dict:
    """The agent's environment: everything except tokens it has no business reading."""
    keep = {"ANTHROPIC_API_KEY"}  # Claude Code itself may need it to authenticate
    return {k: v for k, v in env.items() if k in keep or (k not in SECRET_ENV and not k.endswith(("_TOKEN", "_SECRET", "_API_KEY", "_PASSWORD")))}


def load_template() -> str:
    md = (ROOT / "agents" / "worker_prompt.md").read_text()
    m = re.search(r"<!-- PROMPT START -->\n(.*?)<!-- PROMPT END -->", md, re.S)
    if not m:
        raise RuntimeError("agents/worker_prompt.md is missing its PROMPT START/END markers")
    return m.group(1).strip()


def build_prompt(spec: dict, template: str) -> str:
    out = template
    for k, v in {"REPO": spec["repo"], "ISSUE": str(spec["number"]), "BUG": spec.get("title", ""), "ISSUE_URL": spec.get("issue_url", "")}.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def build_command(claude: str, prompt: str, budget: float) -> list[str]:
    return [claude, "-p", prompt, "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits", "--permission-prompts", "none",
            "--max-budget-usd", f"{budget:.2f}", "--no-session-persistence",
            "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep", "Bash", "--disallowedTools", *DENY]


def describe_tool(block: dict) -> str | None:
    name, inp = block.get("name", ""), block.get("input") or {}
    if name == "Bash":
        return "Ran: " + str(inp.get("command", ""))[:90]
    if name in ("Edit", "Write", "MultiEdit"):
        return "Edited " + str(inp.get("file_path", ""))[-80:]
    return None  # reads and searches are too noisy to show


def parse_stream_line(line: str) -> dict:
    """-> {'events': [str], 'tools': int, 'final': dict|None}"""
    out = {"events": [], "tools": 0, "final": None}
    try:
        d = json.loads(line)
    except ValueError:
        return out
    if d.get("type") == "assistant":
        for b in (d.get("message") or {}).get("content", []) or []:
            if b.get("type") == "tool_use":
                out["tools"] += 1
                t = describe_tool(b)
                if t:
                    out["events"].append(t)
    elif d.get("type") == "result":
        out["final"] = d
    return out


def extract_result(text: str) -> dict | None:
    """The worker ends with a fenced ```json block. Take the last one."""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text or "", re.S)
    for raw in reversed(blocks):
        try:
            d = json.loads(raw)
            if isinstance(d, dict) and d.get("status") in ("fixed", "stopped"):
                return d
        except ValueError:
            continue
    return None


def pr_body_with_footer(body: str, number: int) -> str:
    body = body.strip()
    if not re.search(rf"(fix(es|ed)?|close[sd]?|resolve[sd]?)\s+#{number}\b", body, re.I):
        body += f"\n\nFixes #{number}"
    return body + f"\n\n---\n{DISCLOSURE}"


# ------------------------------------------------------------------ side effects
class Api:
    def __init__(self, server: str, job: str, token: str):
        self.base, self.job, self.h = server.rstrip("/"), job, {"X-Job-Token": token}

    def _r(self, method: str, path: str, **kw):
        r = httpx.request(method, f"{self.base}/api/runner/{self.job}{path}", headers=self.h, timeout=30, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"server said {r.status_code}: {r.text[:200]}")
        return r.json()

    def spec(self): return self._r("GET", "/spec")
    def status(self): return self._r("GET", "/status")
    def event(self, stage: str, text: str):
        try:
            self._r("POST", "/event", json={"stage": stage, "text": text})
        except RuntimeError as e:
            print("  (could not report progress:", e, ")")
    def result(self, payload: dict): return self._r("POST", "/result", json=payload)
    def done(self, pr_url=None, error=None): return self._r("POST", "/done", json={"pr_url": pr_url, "error": error})


def sh(args: list[str], cwd: Path | None = None, check: bool = True, env: dict | None = None) -> str:
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    if check and p.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])} failed: {(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout


def collect_diff(repo_dir: Path) -> tuple[str, list[str]]:
    sh(["git", "add", "-N", "."], repo_dir, check=False)  # make new files visible to `git diff`
    diff = sh(["git", "diff"], repo_dir, check=False)
    files = [l for l in sh(["git", "diff", "--name-only"], repo_dir, check=False).splitlines() if l]
    return diff, files


def run_worker(cmd: list[str], cwd: Path, api: Api, timeout: int) -> tuple[str, dict | None, bool]:
    """Run Claude Code headless, stream progress to the server. Returns (final text, final json, hit_limit)."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=scrub_env(dict(os.environ)))
    start, tools, last_sent, final, text, limit = time.time(), 0, 0.0, None, "", False
    try:
        for line in proc.stdout:
            p = parse_stream_line(line)
            tools += p["tools"]
            for ev in p["events"]:
                if time.time() - last_sent > 1.0:
                    api.event("working", ev)
                    last_sent = time.time()
            if p["final"]:
                final = p["final"]
                text = str(final.get("result") or "")
            if tools > MAX_TOOL_CALLS or time.time() - start > timeout:
                limit = True
                api.event("working", "Reached the safety limit (tool calls or time); stopping the worker.")
                proc.kill()
                break
    finally:
        if proc.poll() is None:
            proc.kill()
    return text, final, limit


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="OSS Mentor local Full-auto runner")
    ap.add_argument("job"); ap.add_argument("token")
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--workdir", default=str(Path.home() / "oss-mentor-jobs"))
    ap.add_argument("--budget", type=float, default=2.0, help="max USD for the Claude Code run")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--claude", default=shutil.which("claude") or "claude")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    a = ap.parse_args(argv)

    for tool in ("gh", "git", a.claude):
        if not shutil.which(tool):
            print(f"Missing required tool: {tool}")
            return 2
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
        print("Run `gh auth login` first.")
        return 2

    api = Api(a.server, a.job, a.token)
    spec = api.spec()
    print(f"Job {spec['id']}: {spec['repo']} #{spec['number']} - {spec['title']}")
    print("\nThis will run the project's build and test commands on THIS machine, driven by an AI agent.")
    print("Only do this for projects you are comfortable running code from (a throwaway VM or container is safer).")
    if not a.yes and input("Type YES to continue: ").strip() != "YES":
        api.done(error="Cancelled at the runner prompt.")
        return 1

    work = Path(a.workdir) / spec["id"]
    work.mkdir(parents=True, exist_ok=True)
    repo_name = spec["repo"].split("/")[1]
    repo_dir = work / repo_name
    try:
        api.event("fork", "Forking the repository to your account…")
        login = sh(["gh", "api", "user", "-q", ".login"]).strip()
        sh(["gh", "repo", "fork", spec["repo"], "--clone", "--remote"], work)
        api.event("clone", "Cloned. Branching from the upstream default branch…")
        default = sh(["gh", "repo", "view", spec["repo"], "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"]).strip() or "main"
        branch = f"fix/{spec['number']}-oss-mentor"
        sh(["git", "fetch", "upstream", default], repo_dir)
        sh(["git", "switch", "-c", branch, f"upstream/{default}"], repo_dir)

        api.event("working", "The worker is reproducing the bug and writing a fix…")
        prompt = build_prompt(spec, load_template())
        text, final, limit = run_worker(build_command(a.claude, prompt, a.budget), repo_dir, api, a.timeout)
        res = extract_result(text) or {}
        diff, files = collect_diff(repo_dir)
        cost = float((final or {}).get("total_cost_usd") or 0)
        status = res.get("status") if res.get("status") in ("fixed", "stopped") else ("fixed" if diff.strip() and not limit else "stopped")
        api.event("review", "Uploading the change for your review…")
        api.result({"status": status, "summary": res.get("summary") or text[-1500:], "diff": diff, "files": files, "tests_run": res.get("tests_run", []),
                    "not_verified": res.get("not_verified", []) + (["Stopped at a safety limit before finishing."] if limit else []),
                    "pr_title": res.get("pr_title") or spec["title"], "pr_body": res.get("pr_body", ""), "cost_usd": cost})
        if status != "fixed" or not diff.strip():
            print("The worker did not produce a verified fix. Nothing was pushed.")
            return 0

        print("\nChange uploaded. Review it in your browser and click Approve to open the PR (waiting)…")
        deadline = time.time() + 4 * 3600
        while time.time() < deadline:
            st = api.status()
            if st["status"] == "approved":
                break
            if st["status"] in ("cancelled", "failed", "expired", "done"):
                print(f"Job is {st['status']}. Stopping; nothing was pushed.")
                return 0
            time.sleep(3)
        else:
            print("Timed out waiting for approval.")
            return 0

        api.event("opening", "Committing and pushing to your fork…")
        sh(["git", "add", "-A"], repo_dir)
        commit = ["git"]
        if not (sh(["git", "config", "user.email"], repo_dir, check=False).strip() and sh(["git", "config", "user.name"], repo_dir, check=False).strip()):
            if st["signoff"]:
                raise RuntimeError("DCO sign-off needs your real name and email: run `git config --global user.name ...` and `user.email ...` first.")
            commit += ["-c", f"user.name={login}", "-c", f"user.email={login}@users.noreply.github.com"]
        commit += ["commit"] + (["-s"] if st["signoff"] else []) + ["-m", st["pr_title"]]
        sh(commit, repo_dir)
        sh(["git", "push", "-u", "origin", branch], repo_dir)
        body_file = work / "pr_body.md"
        body_file.write_text(pr_body_with_footer(st["pr_body"], spec["number"]))
        url = sh(["gh", "pr", "create", "--repo", spec["repo"], "--head", f"{login}:{branch}", "--title", st["pr_title"], "--body-file", str(body_file)], repo_dir).strip().splitlines()[-1]
        api.done(pr_url=url)
        print("PR opened:", url)
        return 0
    except Exception as e:  # report instead of leaving the job hanging
        print("Runner error:", e)
        try:
            api.done(error=str(e)[:400])
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
