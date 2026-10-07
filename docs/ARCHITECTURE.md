# Architecture

Diagrams are Mermaid, so they render on GitHub. A rendered picture of the whole set is in `docs/architecture.png`.
Legend: solid = built and tested; dashed = built but not wired in yet.

## 1. System overview

```mermaid
flowchart TB
  subgraph Browser["Browser (no build step)"]
    direction LR
    UI["React + Tailwind components<br/>Hero, Interview, MatchPodium, DiscoverPanel, ScoutProgress,<br/>IssueBoard, WorkspaceView, RepliesInbox"]
    GAL["Three.js galaxy (scene.js)<br/>planets, hover, blur"]
    LS[("localStorage<br/>step checklists")]
    UI <--> GAL
    UI --- LS
  end

  API["FastAPI app.py<br/>JSON + NDJSON stream API  |  auth.py: GitHub OAuth, per-student token"]

  subgraph Core["Backend modules"]
    direction LR
    MATCH["matcher.py<br/>free scoring"]
    AG["agents.py<br/>scout, explainer, coach"]
    REP["replier.py<br/>classify, draft, gated send"]
    GH["github.py<br/>search, verify, policy scan, discover"]
    LLM["llm.py<br/>tiers, caches, budgets"]
    CAT["catalogue.py<br/>live org catalogue"]
  end

  subgraph Data["Local data (data/)"]
    direction LR
    CACHE[("LLM cache")]
    USAGE[("usage ledger")]
    REPLIES[("reply state")]
    CATFILE[("catalogue.json")]
  end

  subgraph Ext["External services"]
    direction LR
    ANTH["Anthropic API<br/>Haiku 4.5 cheap, Sonnet 5.5 smart"]
    GHAPI["GitHub REST + GraphQL"]
    FEEDS["GSoC, LFX Mentorship,<br/>CNCF landscape, Apache feeds"]
  end

  Browser -->|fetch| API
  API --> MATCH
  API --> AG
  API --> REP
  AG --> GH
  REP --> GH
  AG --> LLM
  REP --> LLM
  MATCH --> CATFILE
  LLM --> ANTH
  LLM --- CACHE
  LLM --- USAGE
  REP --- REPLIES
  GH --> GHAPI
  CAT -.->|refresh| FEEDS
  CAT -.->|enrich| GHAPI
  CAT -.-> CATFILE
```

## 2. Student journey and where each step runs

```mermaid
flowchart TD
  A["Hero"] --> B["Interview: 10 questions"]
  B -->|"answers light up matching planets"| C["Match: score every org"]
  C --> D["Podium: top 3 + 12 runner-ups"]
  D --> E{"Choose org"}
  D -->|optional| D2["Live GitHub search for more projects"]
  D2 --> E
  E --> F["Scout (streamed)<br/>find, verify, rank"]
  F -->|"nothing free"| G["Try next two best orgs"]
  G --> F
  F --> H["Issue board<br/>verified N seconds ago"]
  H -->|"click: re-verify first"| I["Workspace"]
  I --> I1["Repo tour (1 smart call)"]
  I --> I2["Coach or pair chat (1 smart call per turn)"]
  I --> I3["Six step guides (free, static)"]
  I --> J["Student opens PR themselves"]
  J --> K["PR replies: draft, edit, copy or send"]

  classDef free fill:#0f2a1f,stroke:#34d399,color:#e8fff4
  classDef cheap fill:#0e2233,stroke:#38bdf8,color:#e6f4ff
  classDef smart fill:#33200e,stroke:#fb923c,color:#fff1e0
  class B,C,D,D2,H,I3 free
  class F cheap
  class I1,I2,K smart
```
Green = no model tokens. Blue = one cheap-model call. Orange = smart-model call.

## 3. Scouting (why a student always gets a result)

```mermaid
sequenceDiagram
  autonumber
  participant UI as Browser
  participant API as FastAPI
  participant SC as Scout agent
  participant GH as GitHub
  participant LM as Claude (Haiku)

  UI->>API: POST /api/scout/stream (org, profile, fallbacks)
  API->>SC: scout_stream()
  loop org, then up to 2 fallbacks
    SC->>GH: ONE issue search: open, no assignee, -linked:pr, labels
    SC-->>UI: step: found N free issues
    Note over SC,GH: label tiers widen: beginner, help wanted, any unclaimed
    SC->>GH: read AI / contribution policy once per repo
    SC->>GH: per candidate: timeline + recent comments (open PRs, claims)
    SC-->>UI: step: double-checking each issue
    alt candidates survive
      SC->>LM: rank up to 8 for this student
      LM-->>SC: top 3 with fit, learn, risk
      SC-->>UI: result (picks, stats, org_used)
    else nothing free
      SC-->>UI: step: trying the next best match
    end
  end
  UI->>API: POST /api/verify (on click, uncached)
  API->>GH: issue + timeline + comments
  API-->>UI: ok, or the reason it changed
```

## 4. Catalogue pipeline (in progress: built, being wired in)

```mermaid
flowchart LR
  G26["GSoC current year"] --> N
  G25["GSoC previous year"] --> N
  L["LFX Mentorship<br/>paged API"] --> N
  C["CNCF landscape<br/>graduated, incubating, sandbox, popular OSS"] --> N
  A["Apache projects"] --> N
  B["awesome-for-beginners"] --> N
  CUR["Hand-curated list<br/>mentor/orgs.json (119)"] --> M
  N["Normalise<br/>languages, domains, GitHub owner/repo"] --> M["Merge and dedupe"]
  M --> E["Enrich via GitHub GraphQL<br/>free-issue counts, stars, language"]
  E --> R["Auto-rate<br/>beginner, hackathon, setup, brand"]
  R --> F[("data/catalogue.json<br/>refreshed weekly")]
  F --> S["matcher: score thousands, show top 3 + runner-ups"]
  F --> BR["Browse all (search, filter by programme)"]
  CUR --> GAL2["Galaxy: featured set only"]
```
Each feed fails soft: a broken source is reported and skipped, never empties the catalogue. Auto-rated entries are labelled `auto`; curated ones `curated`.

## 5. Identity and tokens

```mermaid
flowchart TD
  S["Student"] -->|"Continue with GitHub"| O["GitHub OAuth<br/>scopes: public_repo, read:user"]
  O --> T["Server session<br/>HttpOnly cookie, token stays on the server"]
  T --> CV["Per-request context<br/>token + student login"]
  CV --> R1["GitHub reads and replies<br/>run as THAT student"]
  CV --> R2["Budget and GitHub cache<br/>keyed by student"]
  CV --> R3["Replies only on the<br/>student's own pull requests"]
```

## 6. Cost control and safety gates

```mermaid
flowchart TD
  P1["1. Deterministic work first<br/>matching, filtering, verification"] --> P2["2. Two tiers<br/>Haiku for triage, Sonnet for teaching"]
  P2 --> P3["3. Disk cache: an identical request is free"]
  P3 --> P4["4. Prompt caching on stable prefixes"]
  P4 --> P5["5. max_tokens caps, low effort, trimmed history"]
  P5 --> P6["6. Session + global USD budgets<br/>checked BEFORE each call"]

  G1["Policy scan before recommending"] --> G2["Sending replies is OFF by default"]
  G2 --> G3["Blocked for projects that restrict AI messages"]
  G3 --> G4["DCO and CLA are signed by the student, never by us"]
```

## 7. Two front doors

```mermaid
flowchart LR
  W["Web app<br/>localhost:8000"] --> SRV["Same backend modules"]
  T["Claude Code terminal<br/>/oss-mentor skill + agents/*.md"] --> FA["Full-auto workers<br/>clone, fix, open PRs on the user's fork"]
  T --> SRV2["Same rules: agents/RULES.md"]
```
The web app covers Learn and Semi-auto. Full-auto runs only in Claude Code because it needs a local checkout and the user's GitHub login.
