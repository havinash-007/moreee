# Project context (share this with the team)

## One-line pitch
An AI mentor that takes a student from "I have never contributed to open source" to "my first pull request is open, I understand it, and I can defend it", with a choice between learning by hand, vibe coding with guardrails, or fully automated agents.

## Why this exists
- Browsing "good first issue" lists fails: popular repos get every easy issue claimed within hours, and many projects now have rules about AI-assisted work.
- Students (and hackathon teams) lose most of their time on setup, picking an issue, and understanding the repo, not on writing code.
- Origin: `oss-bug-hunt`, an automated multi-agent tool that opened 12 PRs across 9 projects in a day. Result: 0 merged at the time of writing. Lesson: volume without understanding does not get merged. This project keeps the verification discipline and adds teaching.

## Users
1. A student with 5-10 hours who wants a first contribution.
2. A hackathon team that wants a real, demo-able contribution in 24-48 hours.
3. (Full-auto mode) An experienced contributor who wants to scale output while supervising.

## The three modes
| Mode | Who codes | Mentor role |
|---|---|---|
| Learn | Student | Coach: hint ladder (question, pointer, sketch). Never gives the full fix. |
| Semi-auto | Student prompts AI, drafts arrive in small chunks | Pair: asks one check question per chunk; student must edit something themselves |
| Full-auto | Worker agents | Coordinator: verifies every PR on GitHub, tracks status |
Details: `learn/modes.md`.

## The flow
10 questions -> deterministic org match (free) -> scout agent finds free issues -> explainer writes a repo tour -> coach/pair guides the fix -> reply assistant helps answer reviewers.

## Architecture
```
Browser UI (frontend/index.html, no build step)
   |  JSON
FastAPI (backend/app.py)
   |-- matcher.py   deterministic org scoring from mentor/orgs.json      (0 tokens)
   |-- github.py    REST client: issues, policy scan, repo overview      (0 tokens)
   |-- agents.py    scout (cheap model), explainer + coach (smart model)
   |-- replier.py   PR comment classify (cheap) + draft (smart) + gated send
   |-- llm.py       Claude wrapper: tiers, disk cache, prompt cache, budgets
```
Claude Code flow (`/oss-mentor`, `.claude/skills/`, `agents/*.md`) is the terminal version and the only place Full-auto workers run, because they need a local checkout, test runs and the user's GitHub login.

## Credit efficiency (what we do and why)
1. **Do not call the model for deterministic work.** Org matching and issue filtering (open, unassigned, labelled, no linked PR) are plain code.
2. **Two model tiers.** Haiku 4.5 for triage and classification; Sonnet 5.5 for teaching and drafting. Configurable in `.env`.
3. **One call per task, batched.** Scouting ranks all candidates in one call. Reply drafting classifies all comments in one call and drafts all replies in one call.
4. **Disk cache.** An identical request is free (`data/cache/`).
5. **Prompt caching.** Top-level `cache_control` on every call so repeated stable prefixes are billed at 0.1x.
6. **Caps.** `max_tokens` per task, effort `low` on the smart model, truncated inputs, chat history trimmed to 6 turns.
7. **Budgets.** Per-session and global USD caps checked before each call using a worst-case estimate, charged from real `usage`. Over budget returns HTTP 402 and the UI shows it. The UI header shows live spend.
Rough per-step cost from the price table (estimates, verify with `/api/usage`): scout about $0.01, repo tour about $0.02, each coach turn about $0.01, reply check about $0.02. A full first-issue session should land well under the default $0.50 cap.

## Accounts and GitHub auth
Students connect their own GitHub (OAuth). Scopes: `public_repo` and `read:user`. Their token stays on the server and is never sent to the browser.
- Reads (issues, policies, PR comments) and any reply run under the student's own token, never the operator's. In hosted mode the server refuses to fall back to a local `gh` login.
- Budgets, usage and the GitHub read cache are per student.
- A student can only draft or send replies on pull requests they authored.
- Cookie is HttpOnly, SameSite=Lax, Secure on https; POSTs from another origin are rejected.
- Setup (operator): create a GitHub OAuth App, set callback `BASE_URL/auth/callback`, put `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `BASE_URL` in `.env`. Without a client id the app runs in single-user local mode.
- Limit: sessions are held in memory, so a restart logs everyone out. Use a database or Redis before real traffic.

## Scouting design (how a student always gets a result)
1. One GitHub issue-search call finds open, unassigned issues with no linked PR across a whole organisation (`org/user/repo` scope). An earlier design made one search per issue, hit GitHub's 30-per-minute search limit and treated the errors as "claimed", which produced empty results.
2. Label tiers widen automatically: beginner labels, then "help wanted", then any unclaimed low-discussion issue.
3. Every candidate is re-checked live (open PR referencing it via the issue timeline, recent "I'll take it" comments). The search alone missed real cases, e.g. an issue with five open PRs.
4. Policies are read once per repo. One cheap-model call ranks the survivors.
5. If an organisation has nothing, the scout tries up to two next-best organisations and tells the student. If all fail, the empty state shows what was searched and offers other matches.
6. Progress streams to the UI as newline-delimited JSON; the student sees each step. Clicking an issue re-verifies it first (`/api/verify`), and cards show how long ago they were verified.

## Full-auto (built: Option A, local runner)
Clicking Full-auto no longer just points at the terminal. The web app runs the gates and supervises; the worker runs on the student's own machine.
- **Gates (all block):** explicit consent; the project's policy must not restrict AI contributions; the issue is re-verified free; one active job per student; 3 jobs per day.
- **Job:** `jobs.py` + SQLite (`data/jobs.db`). Token shown once, stored hashed, prefixed `jt_` (a dash-leading token once broke the CLI).
- **Runner:** `python -m backend.runner <id> <token>`. Forks and clones with the student's `gh`, runs Claude Code headless with `agents/worker_prompt.md`, streams progress, uploads the diff.
- **Agent limits:** may edit files and run the project's build/tests; may not commit, push, use gh/curl/wget/ssh/sudo, or fetch URLs; GitHub/cloud tokens are scrubbed from its environment; capped by tool calls, wall-clock time and `--max-budget-usd`; issue text is treated as data (prompt-injection guard).
- **Review gate:** the student reads a diff viewer, the worker's summary, tests run and an honest "not verified" list, rewrites the PR text, ticks "I can explain every line", confirms any CLA themselves. Diffs containing secrets are blocked.
- **Only after Approve** does the runner commit (`-s` only if the student opted in and has a real git identity), push to *their* fork and open the PR with their own login. An AI-assistance note and "Fixes #N" are appended.
- **Tests:** 28 for jobs and runner, including an offline end-to-end run with fake `gh`/`claude` and local git repos (verifies nothing is pushed before approval, tokens never reach the agent, correct PR arguments, and the failure paths). Not yet run against real GitHub with a real fork.
- **Known limits:** the runner executes a stranger's build/test code on the student's machine (a throwaway VM is safer; a `--docker` option is the next step); the web page polls every 2 seconds rather than streaming; reloading the page after creating a job loses the one-time command.

## Do we need a database?
Today: no for a single local user (files and browser storage cover it). Yes before hosting for several students. What it would hold:
| Data | Now | Problem when hosted |
|---|---|---|
| Login sessions | in memory | Lost on every restart; cannot run two servers |
| Usage and budgets per student | `data/usage.json` + memory | Not per-student on disk; races between workers |
| Student profile, chosen org, journey step, step checklists | browser localStorage | Lost on another device or cleared browser; the team cannot see progress |
| Reply drafts and which comments are handled | `data/replies.json` | Same as above |
| LLM response cache | files in `data/cache` | Fine locally; use Redis or a table with expiry when hosted |
| Audit trail of what was posted to GitHub | none | Needed if auto-posting is ever enabled |
Recommendation: SQLite now (one file, no ops, easy to back up), then PostgreSQL when there are multiple servers. Do not store GitHub tokens in plain text; encrypt them or keep them only in server memory with short sessions.

## Safety and policy decisions (important)
- **The student does their own legal sign-offs.** DCO and CLA are never signed by an agent.
- **Policy scan before recommending.** `github.policy_scan` reads AI_POLICY/AGENTS/CONTRIBUTING and flags AI restrictions. It is a keyword scan, so a hit means "a human must read this", not a verdict. If GitHub cannot be read (rate limit, outage) the error propagates; it must never look like "no restriction".
- **Real finding:** Zulip, our top beginner pick, says not to submit AI-generated PRs you have not personally understood and not to post AI-generated messages in its dev community. So: Learn/Semi modes show a warning chip, Full-auto skips such repos, and the reply assistant refuses to post for them.
- **Auto-reply is draft-first.** The assistant drafts replies; sending is OFF by default (`AUTO_POST_REPLIES=false`), needs a token, needs the human to approve each reply, appends an AI-disclosure line, and is blocked for repos whose policy flags AI.
- **Secrets** live in `.env` (gitignored). The API key is never sent to the browser.

## What is built vs not built
Built: question flow, matcher over a 119-organisation catalogue, live GitHub discovery (`/api/discover`: repos with open good-first-issues in the student's languages/topics, not yet rated or policy-checked), per-step guides in the workspace (commands filled in with the real repo and issue), a gold-on-black editorial theme (Instrument Serif + Manrope, no purple),  scout, repo tour, coach chat, reply drafting and gated send, usage meter and budgets, Claude Code skill, 22 backend tests.
Not built yet: hosted (server-side) Full-auto workers, persistent sessions, a database beyond jobs, rate limiting per user (state is in `data/` files), streaming responses, background polling of PRs for new comments, a hackathon team mode.

## Known limits
- `mentor/orgs.json` (119 orgs) ratings and `legal` fields are judgement and may be wrong; every `legal` on the newer orgs is `varies`. Always verify live. Discovered (live) projects are unrated until scouted.
- Unauthenticated GitHub allows 60 requests/hour; use a token.
- The OAuth flow has been unit-tested with fake sessions but not run against a real GitHub OAuth App. The UI has been syntax-checked and the API smoke-tested, but not yet visually reviewed in a browser or run end-to-end with a real Anthropic key.
- Sonnet/Haiku model IDs and prices are hard-coded defaults; check `backend/config.py` when models change.

## Open questions for the team
1. Do we allow auto-posting at all, or keep reply drafting permanently manual?
2. Hosting: decided as hosted multi-user with GitHub login. Where do we deploy, and who pays the shared API key?
3. Which hackathon format are we targeting first, and does it count contributions to existing projects?
4. Should the org catalogue be curated by us or discovered from GitHub/GSoC lists?

## Run it
```bash
./run.sh            # creates venv, installs deps, copies .env.example to .env
# put ANTHROPIC_API_KEY in .env, run again, open http://localhost:8000
backend tests: .venv/bin/python -m pytest backend -q
```

## File index
| Path | What |
|---|---|
| `backend/llm.py` | Claude wrapper: tiers, caches, budgets |
| `backend/matcher.py` | Free org scoring (top 3 plus 12 runner-ups) |
| `backend/github.py` | GitHub REST + policy scan |
| `backend/agents.py` | Scout, explainer, coach |
| `backend/replier.py` | Reviewer-comment replies |
| `backend/app.py` | API + serves UI; holds the 10 questions |
| `backend/tests/test_core.py` | Tests for matcher, budget, cache, gating |
| `frontend/v2/*.jsx`, `frontend/v2/index.html` | The UI (default): six self-contained components + shell + no-build loader |
| `frontend/scene.js` | Three.js galaxy used by both UIs |
| `frontend/index.html` | Original UI, served at `/classic` |
| `mentor/questions.md`, `mentor/orgs.json` | Rubric and org catalogue |
| `.claude/skills/oss-mentor/SKILL.md` | Terminal mentor flow |
| `agents/*.md` | Role prompts and rules (scout, explainer, coach, pair, worker) |
| `learn/` | Modes, PR template, hackathon playbook |
| `tools/pr_status.py`, `prs.json` | Full-auto PR tracker |
| `archive/` | Original oss-bug-hunt files |
