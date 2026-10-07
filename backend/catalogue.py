"""Live organisation catalogue.

Pulls open-source programmes from public feeds and merges them with our hand-curated list (mentor/orgs.json):
  - Google Summer of Code organisations (current + previous year)   summerofcode.withgoogle.com/api
  - LFX Mentorship projects (Linux Foundation)                       api.mentorship.lfx.linuxfoundation.org
  - CNCF landscape projects (graduated / incubating / sandbox + popular OSS)   landscape.cncf.io
  - Apache Software Foundation projects                              projects.apache.org
  - awesome-for-beginners (beginner-friendly repos, grouped by language)       github.com/MunGell/awesome-for-beginners
Feeds are unofficial/undocumented where noted, so every fetcher fails soft: one broken source never empties the catalogue.
Ratings for ingested entries are AUTO-derived and labelled `rated: "auto"`; curated entries keep `rated: "curated"`.

    python -m backend.catalogue refresh          # fetch, enrich via GitHub, write data/catalogue.json
    python -m backend.catalogue refresh --fast   # skip the GitHub enrichment step
"""
import json
import math
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import config

FILE = config.DATA / "catalogue.json"                          # runtime copy (local use)
SNAPSHOT = config.ROOT / "mentor" / "catalogue_snapshot.json"   # committed copy, shipped with a deployment (read-only hosts)
UA = {"User-Agent": "oss-mentor/1.0 (open-source onboarding tool; catalogue refresh)"}
STALE_AFTER_DAYS = 7
_lock = threading.Lock()
STATE = {"refreshing": False, "last_error": "", "progress": ""}

# ---------------------------------------------------------------- normalisation tables
LANG = {"python": "Python", "javascript": "JavaScript", "js": "JavaScript", "typescript": "TypeScript", "ts": "TypeScript", "java": "Java",
        "go": "Go", "golang": "Go", "rust": "Rust", "c": "C", "c++": "C++", "cpp": "C++", "ruby": "Ruby", "php": "PHP", "kotlin": "Kotlin",
        "swift": "Swift", "dart": "Dart", "c#": "C#", "shell": "Shell", "lua": "Lua", "julia": "Julia", "scala": "Scala", "haskell": "Haskell",
        "elixir": "Elixir", "zig": "Zig", "r": "R", "perl": "Perl", "ocaml": "OCaml", "objective-c": "Objective-C", "html": "HTML", "css": "CSS"}
FRAMEWORK_LANG = {"django": "Python", "flask": "Python", "fastapi": "Python", "numpy": "Python", "pytorch": "Python", "tensorflow": "Python",
                  "pandas": "Python", "react": "JavaScript", "vue": "JavaScript", "angular": "TypeScript", "node": "JavaScript", "nodejs": "JavaScript",
                  "flutter": "Dart", "qt": "C++", "android": "Kotlin", "spring": "Java", "rails": "Ruby", "laravel": "PHP", "wasm": "Rust"}
REAL_LANGS = set(LANG.values())  # anything else (Makefile, Mermaid, Batchfile, HTML...) is not a language a student picks


def top_langs(raw, n: int = 3) -> list[str]:
    """raw: {'Go': bytes, ...}, a list of {'name'} dicts or names. Largest first, real languages only."""
    if isinstance(raw, dict):
        items = sorted(raw.items(), key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 0, reverse=True)
        names = [k for k, _ in items]
    else:
        names = [x.get("name") if isinstance(x, dict) else x for x in (raw or [])]
    out = []
    for nm in names:
        v = LANG.get(str(nm).lower())
        if v in REAL_LANGS and v not in out and v not in ("HTML", "CSS", "Shell"):
            out.append(v)
    return out[:n]


DOMAIN_WORDS = {
    "web": ("web", "frontend", "browser", "http", "react", "vue", "angular", "html", "css", "cms", "website"),
    "ai-ml-data": ("machine learning", "artificial intelligence", " ai", "ai ", "deep learning", "data", "analytics", "nlp", "llm", "neural", "science", "big-data", "search"),
    "cloud-devops": ("cloud", "devops", "kubernetes", "container", "infrastructure", "observability", "serverless", "orchestration", "provisioning", "network", "iot", "messaging", "runtime"),
    "security": ("security", "crypto", "privacy", "vulnerab", "compliance", "authentication", "forensics"),
    "mobile": ("mobile", "android", "ios", "flutter", "react native"),
    "devtools": ("developer tools", "development tools", "compiler", "programming language", "cli", "ide", "editor", "build", "testing", "library", "database", "operating system", "kernel"),
    "education": ("education", "learning", "teaching", "school", "students"),
    "social": ("science", "medicine", "health", "humanitarian", "social", "accessibility", "open data", "climate", "bioinformatics", "civic"),
    "creative": ("game", "graphics", "media", "audio", "video", "music", "art", "creative", "3d", "robotics", "visualization"),
}
GH_URL = re.compile(r"github\.com/(?:orgs/)?([A-Za-z0-9_.-]+)(?:/([A-Za-z0-9_.-]+))?", re.I)  # also matches github.com/orgs/<name>
NOT_OWNERS = {"orgs", "sponsors", "topics", "features", "about", "marketplace", "collections", "apps", "users", "settings"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_json(url: str, params: dict | None = None, timeout: int = 60):
    r = httpx.get(url, params=params, headers=UA, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def gh_ref(*urls) -> tuple[str, str | None] | None:
    """First GitHub owner (and repo) found in the given URLs."""
    for u in urls:
        for url in (u if isinstance(u, (list, tuple)) else [u]):
            m = GH_URL.search(str(url or ""))
            if m and m.group(1).lower() not in NOT_OWNERS:
                repo = (m.group(2) or "").removesuffix(".git") or None
                if "github.com/orgs/" in str(url).lower():
                    repo = None  # /orgs/<name>/people etc: the second segment is a page, not a repository
                return m.group(1), repo
    return None


def txt(x, n: int = 160) -> str:
    """Feeds are inconsistent: a field can be text, a list or a dict. Always return a short string."""
    if isinstance(x, dict):
        x = " ".join(str(v) for v in x.values() if isinstance(v, str))
    elif isinstance(x, (list, tuple)):
        x = " ".join(str(v) for v in x)
    return str(x or "").strip()[:n]


def langs_from(tags) -> list[str]:
    out = []
    for t in tags or []:
        t = str(t).strip().lower()
        for part in re.split(r"[/,]", t):
            part = part.strip()
            v = LANG.get(part) or FRAMEWORK_LANG.get(part)
            if v and v not in out:
                out.append(v)
    return out


def domains_from(*texts) -> list[str]:
    blob = " " + " ".join(str(t).lower() for t in texts if t) + " "
    out = [d for d, words in DOMAIN_WORDS.items() if any(w in blob for w in words)]
    return out[:3] or ["devtools"]


# ---------------------------------------------------------------- fetchers (each returns a list of entries; failures return [])
def entry(name, github, repo=None, **kw):
    e = {"name": name, "github": github, "repo": repo, "languages": [], "domains": [], "notes": "", "sources": [], "gsoc_years": [],
         "lfx": False, "cncf": None, "apache": False, "url": "", "ideas_url": "", "license": "", "stars": None, "pushed": None,
         "gfi": None, "topics": []}
    e.update(kw)
    return e


def fetch_gsoc(year: int) -> tuple[list[dict], list[str]]:
    data = get_json(f"https://summerofcode.withgoogle.com/api/program/{year}/organizations/")
    out, unresolved = [], []
    for o in data:
        ref = gh_ref(o.get("source_code"), o.get("contributor_guidance_url"), o.get("ideas_link"), o.get("website_url"))
        if not ref:
            unresolved.append(o["name"])
            continue
        owner, repo = ref
        use_repo = f"{owner}/{repo}" if repo and gh_ref(o.get("source_code")) else None
        cats = o.get("categories", [])
        langs = langs_from(o.get("tech_tags"))
        doms = domains_from(" ".join(cats), " ".join(o.get("topic_tags", [])), " ".join(o.get("tech_tags", [])))
        out.append(entry(o["name"], owner, use_repo, languages=langs, domains=doms, notes=txt(o.get("tagline")),
                         sources=[f"gsoc{year}"], gsoc_years=[year], url=o.get("website_url") or "", ideas_url=o.get("ideas_link") or "",
                         license=o.get("license") or "", topics=o.get("topic_tags", [])[:6]))
    return out, unresolved


def _page(base: str, key: str | None, log=print) -> dict | None:
    """One LFX page with retries. None = this page is unavailable (the caller keeps what it already has)."""
    for attempt in range(4):
        try:
            return get_json(base, {"nextPageKey": key} if key else None, timeout=40)
        except (httpx.HTTPError, ValueError) as ex:
            log(f"  lfx page failed (attempt {attempt + 1}): {type(ex).__name__}")
            time.sleep(1.5 * (attempt + 1))
    return None


def fetch_lfx(max_pages: int = 120, log=print) -> list[dict]:
    base = "https://api.mentorship.lfx.linuxfoundation.org/projects"
    key, seen, pages = None, {}, 0
    cutoff = time.time() - 2 * 365 * 86400
    while pages < max_pages:
        d = _page(base, key, log)
        if d is None:
            log(f"  lfx: giving up after {pages} pages; keeping {len(seen)} projects found so far")
            break  # a flaky API must not cost us the pages we already have
        for p in d.get("projects", []):
            if p.get("status") != "Published":
                continue
            terms = p.get("programTerms") or []
            if not any((t.get("endDateTime") or 0) > cutoff for t in terms):
                continue  # no recent mentorship term
            ref = gh_ref(p.get("repoLink"), p.get("websiteUrl"))
            if not ref:
                continue
            owner, repo = ref
            k = f"{owner}/{repo}".lower() if repo else owner.lower()
            e = seen.get(k) or entry(p.get("lfProjectName") or owner, owner, f"{owner}/{repo}" if repo else None, lfx=True,
                                      sources=["lfx"], domains=domains_from(p.get("industry"), p.get("name")),
                                      notes=txt(p.get("name")), url=txt(p.get("websiteUrl"), 300))
            e.setdefault("lfx_projects", 0)
            e["lfx_projects"] += 1
            seen[k] = e
        key = d.get("nextPageKey")
        pages += 1
        if not key:
            break
        time.sleep(0.15)
    return list(seen.values())


def fetch_cncf() -> list[dict]:
    d = get_json("https://landscape.cncf.io/data/full.json", timeout=90)
    gh = d.get("github_data", {})
    out = []
    for i in d.get("items", []):
        if not i.get("oss") or not i.get("repositories") or i.get("maturity") == "archived":
            continue
        prim = next((r["url"] for r in i["repositories"] if r.get("primary")), i["repositories"][0]["url"])
        ref = gh_ref(prim)
        if not ref or not ref[1]:
            continue
        g = gh.get(prim, {})
        mat = i.get("maturity")
        if not mat and (g.get("stars") or 0) < 2000:
            continue  # keep non-CNCF landscape entries only when they are popular
        langs = top_langs(g.get("languages"))
        out.append(entry(i["name"], ref[0], f"{ref[0]}/{ref[1]}", languages=langs, cncf=mat or "landscape",
                         domains=domains_from(i.get("category"), i.get("subcategory"), " ".join(g.get("topics") or [])), notes=txt(i.get("summary") or g.get("description")),
                         sources=["cncf"], url=i.get("homepage_url") or "", stars=g.get("stars"), pushed=(g.get("latest_commit") or {}).get("date") if isinstance(g.get("latest_commit"), dict) else None,
                         license=g.get("license") or "", topics=(g.get("topics") or [])[:6]))
    return out


APACHE_CAT = {"big-data": "ai-ml-data", "cloud": "cloud-devops", "web-framework": "web", "network-server": "cloud-devops", "security": "security",
              "http": "web", "library": "devtools", "database": "devtools", "build-management": "devtools", "testing": "devtools", "graphics": "creative",
              "search": "ai-ml-data", "content": "web", "mail": "web", "xml": "devtools", "messaging": "cloud-devops", "iot": "cloud-devops"}


def fetch_apache() -> list[dict]:
    out = []
    for slug, p in get_json("https://projects.apache.org/json/foundation/projects.json").items():
        repo_urls = p.get("repository") or []
        repo_urls = repo_urls if isinstance(repo_urls, list) else [repo_urls]
        ref = gh_ref(repo_urls)
        if not ref or not ref[1]:
            # most ASF projects list gitbox/git-wip URLs; every one is mirrored at github.com/apache/<repo>
            m = next((re.search(r"/([A-Za-z0-9_.-]+?)(?:\.git)?/?$", str(u)) for u in repo_urls if re.search(r"gitbox\.apache\.org|git-wip", str(u))), None)  # svn is not mirrored
            if not m:
                continue
            ref = ("apache", m.group(1))
        cats = p.get("category") or []
        doms = []
        for c in cats:
            d = APACHE_CAT.get(c.lower())
            if d and d not in doms:
                doms.append(d)
        out.append(entry(p.get("name") or slug, ref[0], f"{ref[0]}/{ref[1]}", apache=True, sources=["apache"], languages=langs_from(p.get("programming-language")),
                         domains=doms[:3] or domains_from(" ".join(cats), p.get("shortdesc")), notes=txt(p.get("shortdesc")), url=txt(p.get("homepage"), 300)))
    return out


def fetch_beginner_list() -> list[dict]:
    md = httpx.get("https://raw.githubusercontent.com/MunGell/awesome-for-beginners/main/README.md", headers=UA, timeout=40).text
    out, lang = [], None
    for line in md.splitlines():
        if line.startswith("## "):
            lang = LANG.get(line[3:].strip().lower())
            continue
        m = re.match(r"- \[([^\]]+)\]\((https://github\.com/[^)]+)\)[^<]*(?:<br>\s*(.*))?", line)
        if m:
            ref = gh_ref(m.group(2))
            if ref and ref[1]:
                out.append(entry(m.group(1), ref[0], f"{ref[0]}/{ref[1]}", languages=[lang] if lang else [], sources=["beginner-list"],
                                 domains=domains_from(m.group(3)), notes=txt(m.group(3))))
    return out


BATCH = 10  # smaller GraphQL batches are less likely to be reset or rate-limited


# ---------------------------------------------------------------- enrichment: free-issue counts (+ stars/language) from GitHub GraphQL
def enrich(entries: list[dict], log=print) -> None:
    token = config.GITHUB_TOKEN
    if not token:
        log("  no GitHub token: skipping enrichment")
        return
    todo = [e for e in entries if e["gfi"] is None]
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        parts = []
        for j, e in enumerate(batch):
            scope = f"repo:{e['repo']}" if e["repo"] else f"user:{e['github']}"
            q = f'{scope} is:issue is:open no:assignee -linked:pr archived:false label:\\"good first issue\\",\\"good-first-issue\\",\\"help wanted\\",\\"first-timers-only\\"'
            parts.append(f'a{j}: search(query: "{q}", type: ISSUE, first: 0) {{ issueCount }}')
            if e["repo"]:
                o, r = e["repo"].split("/")
                parts.append(f'r{j}: repository(owner: "{o}", name: "{r}") {{ stargazerCount pushedAt primaryLanguage {{ name }} isArchived }}')
        res = None
        for attempt in range(3):  # GitHub sometimes resets the connection or answers with HTML under load: retry, then move on
            try:
                resp = httpx.post("https://api.github.com/graphql", json={"query": "{ " + " ".join(parts) + " }"},
                                  headers={"Authorization": f"Bearer {token}", **UA}, timeout=60)
                if resp.status_code != 200:
                    raise ValueError(f"HTTP {resp.status_code}")
                res = resp.json()
                break
            except (httpx.HTTPError, ValueError) as ex:
                log(f"  enrichment batch {i // BATCH + 1} attempt {attempt + 1} failed: {type(ex).__name__}")
                time.sleep(2 * (attempt + 1))
        if not res:
            continue  # leave this batch un-enriched; entries keep their defaults
        data = res.get("data") or {}
        for j, e in enumerate(batch):
            a = data.get(f"a{j}")
            if a:
                e["gfi"] = a["issueCount"]
            r = data.get(f"r{j}")
            if e["repo"] and f"r{j}" in data and r is None:
                e["dead"] = True  # GitHub says this repository does not exist: do not offer it to students
            if r:
                e["stars"] = r.get("stargazerCount", e["stars"])
                e["pushed"] = r.get("pushedAt") or e["pushed"]
                pl = (r.get("primaryLanguage") or {}).get("name")
                if pl and not e["languages"] and LANG.get(pl.lower()) in REAL_LANGS:
                    e["languages"] = [LANG[pl.lower()]]
                if r.get("isArchived"):
                    e["dead"] = True
        STATE["progress"] = f"enriching {min(i + BATCH, len(todo))}/{len(todo)}"
        time.sleep(1.0)


# ---------------------------------------------------------------- ratings for auto entries
def rate(e: dict) -> dict:
    mentored = bool(e["gsoc_years"]) or e["lfx"]
    gfi = e["gfi"] or 0
    beginner = 2 + (1 if mentored else 0) + (1 if gfi >= 3 else 0) + (1 if gfi >= 15 else 0)
    recent = False
    if e["pushed"]:
        try:
            recent = (datetime.now(timezone.utc) - datetime.fromisoformat(e["pushed"].replace("Z", "+00:00"))).days < 30
        except ValueError:
            pass
    hack = 3 + (1 if recent else 0) + (1 if gfi >= 15 else 0)
    langs = set(e["languages"])
    stars = e["stars"] or 0
    setup = "heavy" if (langs & {"C", "C++", "Rust"} and stars >= 5000) else "light" if langs and langs <= {"Python", "JavaScript", "TypeScript", "Ruby", "PHP", "Dart", "Go"} and stars < 20000 else "medium"
    brand = 5 if stars >= 20000 else 4 if stars >= 5000 else 3 if stars >= 1000 or e["cncf"] in ("graduated", "incubating") else 2
    if e["cncf"] in ("graduated", "incubating"):
        brand = max(brand, 4)
    e.update({"beginner": max(1, min(5, beginner)), "hackathon": max(1, min(5, hack)), "setup": setup, "brand": brand,
              "gsoc": bool(e["gsoc_years"]), "legal": "varies", "rated": "auto"})
    return e


# ---------------------------------------------------------------- merge + refresh
def key_of(e: dict) -> str:
    return (e["repo"] or e["github"]).lower()


def merge_into(base: dict, new: dict) -> None:
    for s in new["sources"]:
        if s not in base["sources"]:
            base["sources"].append(s)
    base["gsoc_years"] = sorted(set(base.get("gsoc_years", [])) | set(new["gsoc_years"]))
    base["lfx"] = base.get("lfx") or new["lfx"]
    base["cncf"] = base.get("cncf") or new["cncf"]
    base["apache"] = base.get("apache") or new["apache"]
    for f in ("languages", "domains"):
        for v in new[f]:
            if v not in base[f]:
                base[f].append(v)
    for f in ("url", "ideas_url", "license", "notes"):
        base[f] = base.get(f) or new[f]
    for f in ("lfx_projects", "stars", "pushed", "gfi"):
        if base.get(f) is None and new.get(f) is not None:
            base[f] = new[f]


def refresh(enrich_github: bool = True, log=print, target: Path | None = None) -> dict:
    """Fetch all sources, merge, enrich, write data/catalogue.json. Safe to call from a thread."""
    if not _lock.acquire(blocking=False):
        return {"skipped": "already refreshing"}
    STATE.update(refreshing=True, last_error="", progress="starting")
    try:
        year = datetime.now().year
        merged: dict[str, dict] = {}
        counts, unresolved, errors = {}, [], {}

        def add(name, fn):
            STATE["progress"] = f"fetching {name}"
            try:
                res = fn()
                items, unres = res if isinstance(res, tuple) else (res, [])
                counts[name] = len(items)
                unresolved.extend(unres)
                for e in items:
                    k = key_of(e)
                    if k in merged:
                        merge_into(merged[k], e)
                    else:
                        merged[k] = e
                log(f"  {name}: {len(items)}")
            except Exception as ex:  # one broken feed must not empty the catalogue
                errors[name] = f"{type(ex).__name__}: {ex}"[:200]
                log(f"  {name}: FAILED {errors[name]}")

        add(f"gsoc{year}", lambda: fetch_gsoc(year))
        add(f"gsoc{year - 1}", lambda: fetch_gsoc(year - 1))
        add("lfx", fetch_lfx)
        add("cncf", fetch_cncf)
        add("apache", fetch_apache)
        add("beginner-list", fetch_beginner_list)
        if not merged:
            raise RuntimeError("every source failed; keeping the previous catalogue")
        entries = list(merged.values())
        if enrich_github:
            log("  enriching with GitHub (free-issue counts, stars)…")
            try:
                enrich(entries, log)
            except Exception as ex:  # enrichment is a bonus: never lose the fetched catalogue because of it
                log(f"  enrichment aborted: {type(ex).__name__}: {ex}")
        dead = [e["name"] for e in entries if e.get("dead")]
        entries = [e for e in entries if not e.get("dead")]
        if dead:
            log(f"  dropped {len(dead)} missing or archived repositories")
        for e in entries:
            rate(e)
        doc = {"generated_at": now(), "counts": counts, "errors": errors, "unresolved_gsoc": sorted(set(unresolved)), "entries": entries}
        out = target or FILE
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc) if target is None else json.dumps(doc, separators=(",", ":")))
        tmp.replace(out)
        _cached.clear()
        log(f"wrote {len(entries)} entries to {out}")
        return {"entries": len(entries), "counts": counts, "errors": errors}
    except Exception as ex:
        STATE["last_error"] = str(ex)[:300]
        log(f"refresh failed: {ex}")
        return {"error": str(ex)}
    finally:
        STATE.update(refreshing=False, progress="")
        _lock.release()


# ---------------------------------------------------------------- read side
_cached: dict = {}


def _source() -> Path:
    return FILE if FILE.exists() else SNAPSHOT


def load() -> dict | None:
    p = _source()
    try:
        m = (str(p), p.stat().st_mtime)
    except OSError:
        return None
    if _cached.get("m") != m:
        try:
            _cached.update(m=m, doc=json.loads(p.read_text()))
        except (OSError, ValueError):
            return None
    return _cached["doc"]


def status() -> dict:
    d = load()
    age = None
    if d:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(d["generated_at"])).days
    return {"entries": len(d["entries"]) if d else 0, "generated_at": d["generated_at"] if d else None, "age_days": age,
            "counts": d["counts"] if d else {}, "errors": d["errors"] if d else {}, "refreshing": STATE["refreshing"],
            "progress": STATE["progress"], "last_error": STATE["last_error"], "stale": d is None or (age or 0) >= STALE_AFTER_DAYS}


def maybe_refresh_in_background() -> None:
    """Called at server start: refresh when missing or older than a week. Never blocks startup."""
    if config.PUBLIC_DEPLOY:
        return  # serverless hosts cannot persist a refresh; the weekly GitHub Action updates the committed snapshot instead
    if status()["stale"] and not STATE["refreshing"]:
        threading.Thread(target=lambda: refresh(True, log=lambda *_: None), daemon=True, name="catalogue-refresh").start()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        out = refresh(enrich_github="--fast" not in sys.argv, target=SNAPSHOT if "--snapshot" in sys.argv else None)
        print(json.dumps(out, indent=1))
    else:
        print(json.dumps(status(), indent=1))
