# Modes

The student picks a mode in question 1. They can switch at any time ("go semi-auto", "I want to try this one myself").

| | 1. Learn | 2. Semi-auto (vibe code) | 3. Full-auto |
|---|---|---|---|
| Who writes the code | Student | Student prompts AI, AI drafts, student reviews and edits | Worker agent |
| Who opens the PR | Student | Student | Worker agent, on the user's fork, after gates pass |
| Mentor role | Coach: hints only | Pair: explains each AI change, quizzes the student | Coordinator: verifies and reports |
| Agents used | Scout, Explainer | Scout, Explainer, Pair-coder | Scout, Worker, Coordinator, PR checker |
| Best for | Deep learning, interviews | Hackathons with limited time | Experienced contributors, scaling output |
| Understanding gate | Student explains every line | Student explains every line before submit | Student reads the PR summary |
| Typical time per PR | Longest | Medium | Shortest |

## Mode 1: Learn
Hint ladder (question, pointer, sketch). Never paste a full fix. See `agents/coach_prompt.md`.

## Mode 2: Semi-auto (vibe coding with guardrails)
1. Student attempts first, even 10 minutes, and writes down their idea.
2. Student prompts the AI (or the mentor session) for a draft. The AI writes the failing test and fix in small steps, one commit-sized chunk at a time.
3. After each chunk the mentor asks: "What does this do? What could break? Why this and not X?"
4. Student edits the code themselves at least once (rename, handle an edge case, improve a comment).
5. Student runs the tests, writes the PR text in their own words, discloses AI help if the project asks, and opens the PR.
If the student cannot explain a chunk, revert it and go back to Mode 1 for that part.

## Mode 3: Full-auto
Scouts vet issues, one worker per issue reproduces, tests, fixes and opens a PR on the user's fork, and the coordinator verifies everything against GitHub and re-checks PRs on a schedule (`tools/pr_status.py`, `prs.json`).
Hard gates, even in full-auto:
- Never sign a DCO or CLA for the user without their explicit instruction and legal name.
- Skip any project whose policy bans or restricts AI-assisted PRs, or requires human-written PR text.
- Verify the issue is unclaimed immediately before starting; one PR per issue; no pings.
- Truthful PR text, with AI disclosure where asked.
- Stop and report to the human if a gate cannot be passed.
