"""Deterministic organisation matcher. Zero API credits. Mirrors the rubric in mentor/questions.md."""
import json
from functools import lru_cache

from . import config

SETUP = {"light": 1, "medium": 2, "heavy": 3}
MACHINE = {"low": 1, "normal": 2, "docker": 3}
WEIGHTS = {"language": 3, "interest": 3, "beginner": 2, "goal": 2, "setup": 1}


@lru_cache(maxsize=1)
def curated() -> list[dict]:
    """Hand-curated, hand-rated organisations (mentor/orgs.json)."""
    out = json.loads((config.ROOT / "mentor" / "orgs.json").read_text())["orgs"]
    for o in out:
        o.setdefault("rated", "curated")
        o.setdefault("sources", ["curated"])
        o.setdefault("repo", None)
    return out


_merged: dict = {}


def catalogue() -> list[dict]:
    """Curated entries + the live catalogue (GSoC, LFX, CNCF, Apache, beginner lists) when data/catalogue.json exists.
    Curated ratings win; live entries that match a curated one only add their programme badges."""
    from . import catalogue as live
    doc = live.load()
    stamp = (id(doc), len(curated()))
    if _merged.get("stamp") == stamp:
        return _merged["list"]
    base = [dict(o) for o in curated()]
    by_name = {o["name"].lower(): o for o in base}
    by_login = {o["github"].lower(): o for o in base}
    extra = []
    for e in (doc or {}).get("entries", []):
        host = by_name.get(e["name"].lower()) or (by_login.get(e["github"].lower()) if not e["repo"] else None)
        if host:
            live.merge_into(host, e)
            continue
        extra.append(e)
    out = base + extra
    _merged.update(stamp=stamp, list=out)
    return out


def _overlap(mine: list[str], theirs: list[str]) -> float:
    m = {x.lower() for x in mine}
    t = {x.lower() for x in theirs}
    if not m:
        return 0.0
    return min(1.0, len(m & t) / min(len(m), 2))


def score_org(org: dict, p: dict) -> dict:
    skill = p.get("skill", "beginner")
    git = p.get("git_level", "never")
    machine = MACHINE.get(p.get("machine", "normal"), 2)
    goal = p.get("goal", "learn")
    legal_pref = p.get("legal", "both")  # both | dco | unsure

    lang = 5 * _overlap(p.get("languages", []), org["languages"])
    if skill == "beginner" and org["beginner"] <= 2:
        lang *= 0.7
    interest = 5 * _overlap(p.get("interests", []), org["domains"])

    beg = org["beginner"]
    if git in ("never", "commit") and beg < 4:
        beg -= 1
    beg = max(0, min(5, beg))

    if goal == "gsoc":
        g = 5 if org.get("gsoc") else 2
    elif goal == "hackathon":
        g = org["hackathon"]
    elif goal == "job":
        g = org.get("brand", 3)
    else:
        g = org["beginner"]

    gap = SETUP[org["setup"]] - machine
    setup = 5 if gap <= 0 else max(0, 5 - 2 * gap)

    gate = None
    if org.get("legal") == "cla" and legal_pref == "dco":
        gate = "Requires a CLA, but the student only agreed to DCO sign-offs."

    parts = {"language": round(lang, 1), "interest": round(interest, 1), "beginner": beg, "goal": g, "setup": setup}
    total = 0 if gate else round(sum(parts[k] * w for k, w in WEIGHTS.items()), 1)
    return {"org": org["name"], "github": org["github"], "total": total, "max": 55, "parts": parts,
            "gate": gate, "notes": org["notes"], "legal": org.get("legal", "varies"),
            "languages": org["languages"], "domains": org["domains"], "repo": org.get("repo"),
            "sources": org.get("sources", []), "gsoc_years": org.get("gsoc_years", []), "lfx": bool(org.get("lfx")),
            "cncf": org.get("cncf"), "apache": bool(org.get("apache")), "url": org.get("url", ""), "ideas_url": org.get("ideas_url", ""),
            "rated": org.get("rated", "curated"), "stars": org.get("stars"), "gfi": org.get("gfi")}


def rank(profile: dict, top: int = 3) -> list[dict]:
    scored = [score_org(o, profile) for o in catalogue()]
    scored.sort(key=lambda s: s["total"], reverse=True)
    return scored[:top]


def rank_all(profile: dict, top: int = 3, others: int = 24) -> tuple[list[dict], list[dict]]:
    scored = sorted((score_org(o, profile) for o in catalogue()), key=lambda s: s["total"], reverse=True)
    return scored[:top], [s for s in scored[top:top + others] if not s["gate"]]
