"""Settings, read from the environment (.env is loaded in app.py). Nothing secret lives in code."""
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

# Model tiers: cheap model for classification/triage, smart model for teaching and drafting.
MODEL_CHEAP = os.getenv("MODEL_CHEAP", "claude-haiku-4-5")
MODEL_SMART = os.getenv("MODEL_SMART", "claude-sonnet-5-5")

# USD per million tokens (input, output). Cache reads cost 0.1x input, cache writes 1.25x.
PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
DEFAULT_PRICE = (4.0, 20.0)  # unknown model: assume the expensive tier

SESSION_BUDGET_USD = float(os.getenv("SESSION_BUDGET_USD", "0.50"))
GLOBAL_BUDGET_USD = float(os.getenv("GLOBAL_BUDGET_USD", "10.00"))

def _github_token() -> str:
    """Env var first; otherwise reuse the local `gh` login for read access (60 req/h unauthenticated is too low)."""
    t = os.getenv("GITHUB_TOKEN", "")
    if t:
        return t
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


GITHUB_TOKEN = _github_token()
# Posting replies on GitHub is off unless explicitly enabled by the operator.
AUTO_POST_REPLIES = os.getenv("AUTO_POST_REPLIES", "false").lower() == "true"
AI_DISCLOSURE = os.getenv("AI_DISCLOSURE", "Drafted with AI assistance and reviewed by the author.")
