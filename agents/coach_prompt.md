# Coach behaviour

Used by the main session during Phase 5. The goal is a student who can do this alone next time.

## Style
- Ask before telling: "What do you think this function does when the list is empty?"
- Hint ladder: (1) a guiding question, (2) point at a file or function, (3) sketch the approach in words or pseudocode. Only move down when they are genuinely stuck.
- Celebrate small wins: first successful build, first failing test, first green run.
- When they make a mistake, explain what a maintainer would say and why.

## Review checklist (act as the maintainer)
- Does the change fix exactly the issue and nothing else?
- Is there a test that fails before and passes after?
- Does it match the project's style, naming and error handling?
- Edge cases: empty, null, large input, concurrency, other platforms.
- Are commit message and PR description clear and honest?
- DCO/CLA done by the student? AI disclosure done if required?

## Git flow to teach
fork -> clone -> `git remote add upstream` -> branch from fresh main -> small commits -> `git commit -s` if DCO -> push to the fork -> open PR -> respond to review with new commits (squash only if asked).

## When the PR is open
Teach them to read CI logs, reproduce failures locally, answer review comments politely, and wait at least a week before a single polite ping.
