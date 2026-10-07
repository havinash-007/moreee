# Interview questions

Ask in this order. Each has options plus free text ("Other").

| # | Question | Options | Used for |
|---|---|---|---|
| 1 | Which mode do you want? | Learn (I code, you coach) / Semi-auto (I vibe code with AI, you quiz me) / Full-auto (agents do it, I supervise) | mode (`learn/modes.md`) |
| 2 | Which programming languages can you read comfortably? | Python / JavaScript-TypeScript / Java-Kotlin / Go / Rust / C-C++ / (multi) | language fit |
| 3 | How would you rate your skill in your best language? | Beginner (courses only) / Intermediate (built projects) / Advanced | difficulty ceiling |
| 4 | What are you most curious about? | Web apps / AI-ML-data / Cloud-DevOps / Security / Mobile / Developer tools / Docs-education | interest fit |
| 5 | What is your main goal? | Hackathon / Internship-job / Google Summer of Code / Learn and build portfolio | goal fit |
| 6 | How much time do you have, and when is the deadline? | <5 h/week / 5-10 h/week / 10+ h/week; hackathon date if any | scope of issue |
| 7 | How comfortable are you with Git and GitHub? | Never used / commit and push only / branches and PRs / fork and rebase | how much teaching is needed |
| 8 | What kind of first contribution do you want? | Bug fix / Docs / Tests / Small feature / Any, pick for me | issue type |
| 9 | What can your machine run? | Low-spec laptop / Normal laptop / Can run Docker and big builds | setup fit |
| 10 | Are you OK with legal sign-offs (DCO or CLA) and disclosing AI help when a project asks? | Yes to both / DCO only / Not sure, explain it to me | policy fit |

## Scoring rubric

Score each org in `orgs.json` from 0-5 on each line, then weight:

| Factor | Weight | How |
|---|---|---|
| Language fit | x3 | Org has repos in the student's languages (Q2) at their level (Q3) |
| Interest fit | x3 | Org's domain tags match Q4 |
| Beginner-friendliness | x2 | `beginner` rating in the catalogue, adjusted by Q7 |
| Goal fit | x2 | goal (Q5): GSoC participant for GSoC, `hackathon` rating for hackathon, brand value for job |
| Setup fit | x1 | Build weight (`setup`) vs Q9 |
| Policy fit | gate | Fail (score 0) if Q10 conflicts with the org's DCO/CLA/AI rules |

Max 55. Report the breakdown so the student sees *why*.
