"""
smoke_test.py — end-to-end smoke run for the 2026 FIFA World Cup tracker.

Uses a temp dir so it never touches the real state.json / docs/.
No Telegram sends (token=""). No git calls.

Usage:
    ./venv/bin/python scripts/smoke_test.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Ensure the repo root is on sys.path so `from src import tracker` resolves
# regardless of where this script is invoked from.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src import tracker  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic results for 2026-06-11 (opening matchday)
# ---------------------------------------------------------------------------

def _load_opening_match_ids() -> list[str]:
    """Return the seed IDs for matches played on 2026-06-11."""
    fixtures_path = REPO_ROOT / "data" / "fixtures.json"
    with open(fixtures_path) as fh:
        seed = json.load(fh)
    return [m["id"] for m in seed["matches"] if m.get("date") == "2026-06-11"]


def _synthetic_results(match_ids: list[str]) -> dict:
    """Fabricate completed results keyed by seed id."""
    # Two hardcoded results — realistic enough to exercise every code path.
    defaults = [
        {"home_goals": 2, "away_goals": 1, "status": "FT"},
        {"home_goals": 0, "away_goals": 0, "status": "FT"},
    ]
    out: dict = {}
    for i, sid in enumerate(match_ids):
        out[sid] = defaults[i % len(defaults)]
    return out


# ---------------------------------------------------------------------------
# Main smoke run
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== FIFA 2026 tracker smoke test ===\n")

    # 1. Read real seed IDs so keys are valid.
    match_ids = _load_opening_match_ids()
    print(f"Opening matchday IDs (2026-06-11): {match_ids}")

    synthetic = _synthetic_results(match_ids)
    print(f"Synthetic results: {synthetic}\n")

    # 2. Temp working dir — never touches real state.json / docs/.
    tmpdir = tempfile.mkdtemp(prefix="fifa2026_smoke_")
    tmp = Path(tmpdir)
    state_path = tmp / "state.json"
    html_path  = tmp / "index.html"
    cache_path = tmp / "cache" / "results.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Temp dir: {tmpdir}")

    # 3. Capture would-be sends (no real Telegram).
    sends: list[str] = []

    def fake_sender(text: str, **kwargs) -> bool:
        sends.append(text)
        return True

    cfg = tracker.Config(
        state_path=state_path,
        html_path=html_path,
        cache_path=cache_path,
        token="",                        # no real sends
        chat_ids=[],
        fetch=lambda: synthetic,
        sender=fake_sender,
        now_iso="2026-06-11",
        sim_iters=200,                   # fast
    )

    # 4. Run the tracker.
    exit_code = tracker.run(cfg)

    # 5. Read the saved state to inspect message types.
    with open(state_path) as fh:
        saved_state = json.load(fh)

    message_types: list[str] = []
    for day in saved_state.get("days", []):
        for msg in day.get("messages", []):
            message_types.append(msg["type"])

    html_size = html_path.stat().st_size if html_path.exists() else 0

    print("\n--- Results ---")
    print(f"Exit code          : {exit_code}")
    print(f"Message types      : {message_types}")
    print(f"Would-be Tg sends  : {len(sends)}")
    print(f"HTML path          : {html_path}")
    print(f"HTML size (bytes)  : {html_size}")

    # 6. Assertions.
    errors: list[str] = []

    if exit_code != 0:
        errors.append(f"Expected exit code 0, got {exit_code}")

    if "morning_brief" not in message_types:
        errors.append("No 'morning_brief' message was generated")

    if html_size == 0:
        errors.append("HTML file is empty or missing")

    if errors:
        print("\nFAILURE:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("\nSMOKE OK")


if __name__ == "__main__":
    main()
