"""Claude wrapper built to spend as little as possible.

Savings, in order of impact:
1. Deterministic work (org matching, issue filtering) never calls the model.
2. Two tiers: a cheap model for triage/classification, a smart model for teaching and drafting.
3. Disk cache: an identical request is answered for free.
4. Prompt caching (`cache_control`) on the large, stable prefix of repeat calls.
5. Hard `max_tokens` per task, low effort on the smart model, trimmed inputs.
6. Per-session and global USD budgets, checked before every call and charged from real usage.
"""
import hashlib
import json
import threading
from dataclasses import dataclass, field

import anthropic

from . import config

CACHE_DIR = config.DATA / "cache"
CACHE_DIR.mkdir(exist_ok=True)
USAGE_FILE = config.DATA / "usage.json"
_lock = threading.Lock()


class BudgetExceeded(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    cache_hits: int = 0  # answered from the disk cache, cost nothing

    def as_dict(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


@dataclass
class Ledger:
    sessions: dict[str, Usage] = field(default_factory=dict)
    total: Usage = field(default_factory=Usage)

    def session(self, sid: str) -> Usage:
        return self.sessions.setdefault(sid, Usage())


ledger = Ledger()


def _load_total() -> None:
    try:
        ledger.total = Usage(**json.loads(USAGE_FILE.read_text()))
    except (OSError, ValueError, TypeError):
        pass


_load_total()


def cost_of(model: str, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> float:
    pin, pout = config.PRICES.get(model, config.DEFAULT_PRICE)
    return (inp * pin + out * pout + cache_read * pin * 0.1 + cache_write * pin * 1.25) / 1_000_000


def estimate_input_tokens(*texts: str) -> int:
    return sum(len(t) for t in texts) // 3 + 1  # deliberately pessimistic (chars/3)


def _charge(u: Usage, model: str, usage) -> float:
    inp = usage.input_tokens or 0
    out = usage.output_tokens or 0
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    c = cost_of(model, inp, out, cr, cw)
    u.input_tokens += inp
    u.output_tokens += out
    u.cache_read_tokens += cr
    u.cache_write_tokens += cw
    u.cost_usd += c
    u.calls += 1
    return c


def _check_budget(session_id: str, model: str, est_in: int, max_tokens: int) -> None:
    worst = cost_of(model, est_in, max_tokens)
    s = ledger.session(session_id)
    if s.cost_usd + worst > config.SESSION_BUDGET_USD:
        raise BudgetExceeded(
            f"Session budget ${config.SESSION_BUDGET_USD:.2f} would be exceeded "
            f"(spent ${s.cost_usd:.4f}, this call could cost up to ${worst:.4f})."
        )
    if ledger.total.cost_usd + worst > config.GLOBAL_BUDGET_USD:
        raise BudgetExceeded(f"Global budget ${config.GLOBAL_BUDGET_USD:.2f} reached.")


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


def ask(
    *,
    tier: str,
    system: str,
    messages: list[dict],
    max_tokens: int,
    session_id: str = "default",
    effort: str = "low",
    use_cache: bool = True,
) -> dict:
    """Return {"text", "model", "cost_usd", "cached"}. `tier` is "cheap" or "smart"."""
    model = config.MODEL_CHEAP if tier == "cheap" else config.MODEL_SMART
    key = hashlib.sha256(json.dumps([model, system, messages, max_tokens], sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    if use_cache and path.exists():
        with _lock:
            ledger.session(session_id).cache_hits += 1
            ledger.total.cache_hits += 1
        return {"text": json.loads(path.read_text())["text"], "model": model, "cost_usd": 0.0, "cached": True}

    est = estimate_input_tokens(system, json.dumps(messages))
    with _lock:
        _check_budget(session_id, model, est, max_tokens)

    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system}],
        messages=messages,
        cache_control={"type": "ephemeral"},  # caches the stable prefix across repeat calls
    )
    if tier != "cheap":
        kwargs["output_config"] = {"effort": effort}  # Haiku 4.5 does not accept effort

    resp = client().messages.create(**kwargs)
    text = "".join(b.text for b in resp.content if b.type == "text")
    if resp.stop_reason == "refusal":
        text = ""
    with _lock:
        c = _charge(ledger.session(session_id), model, resp.usage)
        _charge(ledger.total, model, resp.usage)
        USAGE_FILE.write_text(json.dumps(ledger.total.as_dict()))
    if use_cache and text:
        path.write_text(json.dumps({"text": text}))
    return {"text": text, "model": model, "cost_usd": c, "cached": False}


def parse_json(text: str):
    """Pull the first JSON object/array out of a model reply."""
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start == -1:
        raise ValueError("no JSON in reply")
    dec = json.JSONDecoder()
    obj, _ = dec.raw_decode(text[start:])
    return obj
