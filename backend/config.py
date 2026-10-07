"""Settings, read from the environment (.env is loaded in app.py). Nothing secret lives in code."""
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ON_VERCEL = bool(os.getenv("VERCEL"))
# A public deployment must never run in the single-user "local" mode (anyone could spend the operator's keys).
PUBLIC_DEPLOY = ON_VERCEL or os.getenv("PUBLIC_DEPLOY", "").lower() == "true"
# Serverless filesystems are read-only except /tmp, which is per-instance and ephemeral: only caches may live there.
DATA = Path(os.getenv("DATA_DIR") or ("/tmp/oss-mentor" if ON_VERCEL else ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)

# State that must survive between requests/instances lives in Postgres when DATABASE_URL (or Vercel's POSTGRES_URL) is set; SQLite otherwise.
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""
# Signs and encrypts the sign-in cookie, so sessions work across serverless instances with no server-side session store.
SECRET_KEY = os.getenv("SECRET_KEY", "")

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

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")


def _github_token() -> str:
    """Env var first; otherwise reuse the local `gh` login for read access (60 req/h unauthenticated is too low)."""
    t = os.getenv("GITHUB_TOKEN", "")
    if t:
        return t
    if GITHUB_CLIENT_ID:
        return ""  # hosted mode: never fall back to the operator's identity
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


GITHUB_TOKEN = _github_token()
# Posting replies on GitHub is off unless explicitly enabled by the operator.
AUTO_POST_REPLIES = os.getenv("AUTO_POST_REPLIES", "false").lower() == "true"
AI_DISCLOSURE = os.getenv("AI_DISCLOSURE", "Drafted with AI assistance and reviewed by the author.")


def deploy_missing() -> list[str]:
    """What a PUBLIC deployment still needs before it may serve requests. Empty list = safe to serve (or not a public deployment)."""
    if not PUBLIC_DEPLOY:
        return []
    need = []
    if not (GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET):
        need.append("GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET (a GitHub OAuth App, so only signed-in students can use your API keys)")
    if len(SECRET_KEY) < 32:
        need.append("SECRET_KEY (at least 32 random characters)")
    if not DATABASE_URL:
        need.append("DATABASE_URL (a Postgres database such as Neon)")
    return need
