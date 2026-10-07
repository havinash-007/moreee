"""Deterministic organisation matcher. Zero API credits. Mirrors the rubric in mentor/questions.md."""
import json
from functools import lru_cache

from . import config

SETUP = {"light": 1, "medium": 2, "heavy": 3}
MACHINE = {"low": 1, "normal": 2, "docker": 3}
WEIGHTS = {"language": 3, "interest": 3, "beginner": 2, "goal": 2, "setup": 1}


@lru_cache(maxsize=1)
def catalogue() -> list[dict]:
    return json.loads((config.ROOT / "mentor" / "orgs.json").read_text())["orgs"]


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
            "languages": org["languages"], "domains": org["domains"]}


def rank(profile: dict, top: int = 3) -> list[dict]:
    scored = [score_org(o, profile) for o in catalogue()]
    scored.sort(key=lambda s: s["total"], reverse=True)
    return scored[:top]


def rank_all(profile: dict, top: int = 3, others: int = 12) -> tuple[list[dict], list[dict]]:
    scored = sorted((score_org(o, profile) for o in catalogue()), key=lambda s: s["total"], reverse=True)
    return scored[:top], [s for s in scored[top:top + others] if not s["gate"]]
