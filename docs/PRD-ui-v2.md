# PRD: OSS Mentor UI v2

Status: **Superseded in part.** The owner chose bold standalone components (no Vite/React rebuild, no build step) instead of the section 11 approach. Screens, journey and design principles below still guide the UI; the shipped components live in `frontend/v2/`.
Owner: Havinash. Scope: the student-facing web UI (`frontend/`). Backend API stays as is, plus the small additions listed in section 11.

---

## 1. Why a v2

The current UI works but does not feel like a product. Honest critique of v1 (from screenshots):

| Problem in v1 | Why it matters |
|---|---|
| The first thing a student sees is a red operator error ("No Anthropic API key") | Students cannot fix it and it looks broken |
| Header is a floating strip: logo and spend meter sit far apart, nothing aligns with the content column | Looks unfinished |
| Everything is a text-heavy card in a 540px column | Hard to scan; no hierarchy; no sense of progress |
| 3D planets are decoration. Hovering tells you little and answering questions does nothing to them | The most memorable element carries no meaning |
| Score breakdown is five identical bars | Does not explain *why* an org won |
| No visible journey (where am I, what is next) | Students get lost after "Choose" |
| Coaching is a plain chat box under a wall of markdown | The most valuable step is the plainest |
| Policy, legal and safety info is tiny chips | The most important trust signals are the least visible |
| Not designed for phones | Many students will use a phone first |

## 2. Product goal

A student who has never contributed to open source should, within one sitting, feel: *"I know where to start, I understand this codebase, and I am not alone."* The UI must make the **journey legible**, the **recommendations explainable**, and the **coaching the hero**.

### Success measures (proposed targets, to be validated)
- 80% of first-time visitors who press Start finish the interview.
- 60% of those who finish choose an issue.
- Median time from landing to chosen issue under 10 minutes.
- Zero student-visible operator errors (all operator problems go to an admin surface).
- Lighthouse accessibility score of 95 or higher; WCAG 2.2 AA contrast.

## 3. Users

1. **First-timer** (primary): knows one language, never used a PR. Needs reassurance and plain language.
2. **Hackathon team member**: short on time, wants the fastest path to a demo-able contribution.
3. **Experienced contributor** (full-auto mode): wants a dashboard of agents and PRs, not hand-holding.
4. **Operator/admin** (you): sets keys, budgets, sees spend. Never shown to students.

## 4. Design principles

1. **Show the journey.** Always visible: where you are, what is done, what is next.
2. **Explain, don't just rank.** Every recommendation says why in one plain sentence.
3. **The 3D has a job.** The galaxy is a live model of the student's profile: it reacts to every answer. It is never just wallpaper, and it recedes when the student needs to read or code.
4. **Trust is visible.** Policy, legal sign-off and "verified just now" checks are first-class UI, not footnotes.
5. **Teach in the flow.** Coaching sits next to the work, not below a document.
6. **Calm, fast, accessible.** Keyboard first, reduced-motion respected, readable at 16px on a phone.

## 5. Visual direction

- **Mood:** deep-space dark with one warm accent. Quiet confidence, not neon.
- **Colour tokens:** background `#0B0D14`, surface `#12151F`, raised `#181C2A`, line `#252A3B`, text `#E8EAF2`, muted `#98A0B8`, accent `#7C8CFF`, success `#34D399`, warning `#FBBF24`, danger `#F87171`. Domain colours (web, AI/data, cloud, security, mobile, devtools, education) are used only on planets and small dots, never as button colours.
- **Type:** Inter (UI), JetBrains Mono (code). Scale 12/14/16/20/28/40; weights 400 and 600 only. Line height 1.5 body, 1.15 headings.
- **Layout grid:** 12 columns, 1200px max content, 24px gutters desktop, 16px mobile. Spacing scale 4/8/12/16/24/32/48.
- **Shape:** radius 16 on cards, 10 on controls. Elevation by surface colour and 1px border, not heavy shadows.
- **Glass:** only on overlays (tooltip, drawers), never on reading surfaces.
- **Motion:** 150-250ms ease-out for UI, 600-900ms for camera moves. Everything has a reduced-motion variant that cuts instantly. No motion longer than 1s blocks interaction.
- **Icons:** one set (Lucide), 1.5px stroke.

## 6. Information architecture

```
Landing  ->  Interview  ->  Matches  ->  Issues  ->  Workspace  ->  Replies
                                                       (Understand, Reproduce, Fix, Test, PR, Review)
Persistent: top bar (logo, journey progress, mode, usage pill, account)
Admin (separate route, operator only): keys, budgets, usage, policy flags
```

## 7. Screens

### 7.1 Landing
Full-bleed galaxy. Left: headline "Your first open-source pull request, with a mentor", one sentence, one primary button **Start (2 min)**, secondary "How it works" (3-step strip). Subtext: "No sign-up needed to explore."
- Galaxy is explorable (drag, hover) but quiet; labels only on hover.
- No errors, no banners.

### 7.2 Interview (signature interaction)
One question per screen, large tappable choices with icons, keyboard 1-9 to select, Enter to continue, progress as 10 dots.
- **The galaxy answers back:** choosing "Python" lights up every org with Python and dims the rest; interests tint planets; "low-spec laptop" shrinks heavy-setup planets. A small live counter says "9 organisations still fit you".
- Right-side "Your profile so far" chip stack (editable by click).
- Back is always possible; answers persist if the tab closes.

### 7.3 Matches
A podium: #1 centre and larger, #2 and #3 beside it. Each card:
- Org name, one-line "why this fits you" written from the score parts (e.g. "Matches your Python, web interest and beginner level; setup is light for your laptop").
- A **radar chart** of the five factors instead of bars, with the weakest factor called out ("Heavier setup than your machine ideally wants").
- Badges: legal (CLA/DCO), GSoC, AI policy status.
- **Compare** toggle to overlay two radars.
- Click a planet or a card to open an org drawer (notes, languages, sample repos). Primary action: **Find me an issue here**.
- "Verified live" strip appears after scouting starts (see 7.4).

### 7.4 Issues (scout results)
- While scouting, show the real checks ticking live: *Reading policies... Filtering unassigned issues... Checking for existing PRs... Ranking for you...*. Cost is shown after ("This search cost $0.01").
- Result: up to 3 issue cards on a board. Each shows: title, repo, estimated hours, "what you will learn", difficulty dots, and a **checklist**: unassigned, no linked PR, policy read, tests available, last maintainer activity.
- **Policy panel is prominent:** if the repo restricts AI, a coloured banner explains in plain words what that means for this student's mode (e.g. "You must write and understand every line, and not post AI-written comments"), with the exact quoted line and a link.
- Legal sign-off explained in a one-line tooltip with a "what is a CLA?" popover.
- Primary: **Start working on this**. Secondary: "Show me different issues".

### 7.5 Workspace (the heart)
Three panes on desktop, tabbed on mobile.
- **Left: journey stepper.** Understand, Reproduce, Fix, Test, Open PR, Review. Each step has a short "done when" checklist the student ticks; the mentor can also tick it.
- **Centre: tabs** - *Tour* (rendered repo tour with a working mermaid architecture diagram, collapsible sections, "files to read first" as links), *Coach* (chat), *Notes*. The coach chat shows hint level used (1 question, 2 pointer, 3 sketch), a "give me a bigger hint" button, and in semi-auto mode shows each AI chunk as a code card with an "Explain it back" prompt before the next chunk unlocks.
- **Right: context.** Issue summary, quick links (issue, repo, CONTRIBUTING), the PR description builder (template with their own words), sign-off reminder, spend for this issue.
- 3D recedes to a faint background (about 15% intensity), with the chosen org as a small planet in the corner that acts as a home button.

### 7.6 PR replies
Inbox layout: list of new reviewer comments on the left, selected comment with code context and the draft reply on the right.
- Each comment tagged (actionable, question, nit, praise), with "needs a code change" flagged and a link to the exact file and line.
- Draft is an editable text area with a diff against "your own words" nudge; a banner states clearly if sending is disabled or blocked by the project's AI policy and shows the quoted rule.
- Copy, mark done, and (if enabled) Approve and send.

### 7.7 Full-auto dashboard (phase 2)
Table of agents and PRs with status (open, CI failing, changes requested, merged), the verified-on-GitHub timestamp, and a pause-all control.

### 7.8 Admin (operator only)
Separate route behind an admin allow-list. Shows key status, models, budgets, per-student spend, policy flags. This is where "missing API key" lives; students instead see a friendly "The mentor is resting, try again soon" if the service is unavailable.

## 8. States every screen must handle
Loading (skeletons, never spinners alone), empty, error with a plain-language recovery action, offline, rate-limited ("GitHub is busy, retrying in 20s"), **budget reached** ("You have used today's free mentor time. You can keep going with hints you already have"), signed-out, and no-WebGL.

## 9. Responsive and accessibility
- Breakpoints 360, 768, 1200. Mobile: single column, stepper becomes a bottom sheet, galaxy becomes a short hero strip rather than a full background.
- Keyboard: full tab order, visible focus ring, shortcuts for interview and stepper; every 3D action has a button equivalent.
- Contrast AA; no meaning by colour alone (badges carry text/icons).
- `prefers-reduced-motion`: no auto-rotate, instant camera moves. A visible "Reduce 3D" toggle.
- Screen-reader: live region for scouting progress and new coach messages.

## 10. 3D requirements
- Three.js, vanilla (no heavy wrappers). Load under 1.5s on a mid laptop; cap at 60fps, drop to 30fps and then to static on low power.
- States: *explore* (landing), *respond* (interview, planets react), *podium* (matches), *focus* (chosen org), *ambient* (workspace). Smooth transitions between them.
- Fixes from v1: no stretched planets (narrow FOV), no overlap with text (scene offset away from content), labels only on hover or focus, legend moved out of the way.
- Performance guard: pause when the tab is hidden; pixel ratio capped at 2.

## 11. Technical approach and backend additions

**Recommendation:** rebuild the front end with **Vite + TypeScript + React + Tailwind**, three.js vanilla in its own module, charts with a small SVG radar component. FastAPI serves the built `dist/`. Reasoning: seven screens with shared state, a stepper, drawers and a chat are painful in one hand-written HTML file.

Alternative (cheaper, less polished): keep vanilla JS and split into modules. Not recommended.

Backend additions (small):
1. `POST /api/match` returns, per org, a `why` sentence and `weakest` factor (deterministic, no tokens).
2. `GET /api/scout/stream` (server-sent events) so the checks tick live.
3. `GET /api/admin/*` behind an admin allow-list (key status, spend).
4. Persist student profile and journey step server-side (SQLite) so progress survives a refresh. Optional in phase 1 (localStorage first).
5. Health endpoint split: public status (friendly) vs admin status (detailed).

## 12. Phasing

| Phase | Scope | Result |
|---|---|---|
| 1 | Design tokens, app shell, landing, interview with galaxy reacting, matches podium, admin split | A student can finish the interview and get explained matches |
| 2 | Issues board with live checks, workspace (stepper, tour, coach, PR builder) | The core mentoring journey |
| 3 | PR replies inbox, mobile polish, accessibility pass | Whole product usable on phone |
| 4 | Full-auto dashboard, persistence, analytics | Power-user and team features |

## 13. Out of scope
User-generated org catalogue, in-browser code editor or terminal, native apps, payments, multi-language UI, light theme.

## 14. Risks
- The galaxy distracts from the task: mitigated by the ambient state and a Reduce 3D toggle.
- Live-check animations imply certainty the scan cannot give: copy must say "found no restriction" and always link the source, never "approved".
- A rewrite delays shipping: mitigated by phase 1 being independently shippable.
- Model cost spikes in the workspace: usage pill plus per-issue budget, already enforced by the backend.

## 15. Decisions needed from you

| # | Decision | My recommendation |
|---|---|---|
| 1 | Framework: React + Vite + TS + Tailwind, or stay vanilla | React stack |
| 2 | Visual mood: deep-space dark with one warm accent, or something lighter/friendlier | Deep-space dark, as specced |
| 3 | Is the galaxy reacting to answers (7.2) the signature interaction? | Yes |
| 4 | Mobile: full galaxy or short hero strip | Hero strip |
| 5 | Persistence in phase 1: localStorage, or SQLite now | localStorage first |
| 6 | Light theme: out of scope for now | Agree |
| 7 | Phase order above | Agree |

**Acceptance:** reply "accepted" (or list changes by number, e.g. "2: lighter, 4: full galaxy") and I will start phase 1.
