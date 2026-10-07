"""Report status and score of pull requests listed in prs.json.

Score: merged = +1, closed without merge = -1, open = 0.
Requires the GitHub CLI (`gh`) to be authenticated.
"""

import json
import subprocess
import sys
from pathlib import Path


def fetch(repo: str, number: int) -> dict:
    """Return state info for one PR via `gh pr view`."""
    out = subprocess.run(
        ["gh", "pr", "view", str(number), "-R", repo,
         "--json", "state,mergedAt,reviewDecision,title"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def score(info: dict) -> int:
    """Map PR state to a score."""
    if info["mergedAt"]:
        return 1
    return -1 if info["state"] == "CLOSED" else 0


def main(path: str = "prs.json") -> None:
    prs = json.loads(Path(path).read_text())
    total = 0
    for p in prs:
        info = fetch(p["repo"], p["number"])
        s = score(info)
        total += s
        status = "MERGED" if info["mergedAt"] else info["state"]
        print(f'{p["repo"]}#{p["number"]:<6} {status:<8} {s:+d}  {info["title"][:60]}')
    print(f"Total: {total:+d}")


if __name__ == "__main__":
    main(*sys.argv[1:])
