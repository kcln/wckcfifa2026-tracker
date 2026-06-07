"""Load the seeded schedule and merge live results onto it."""
from __future__ import annotations
import copy, json
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "fixtures.json"


def load_seed(path: Path = SEED_PATH) -> dict:
    return json.loads(Path(path).read_text())


def merge_results(seed: dict, live: dict) -> dict:
    """live maps match id -> {home_goals, away_goals, status}. Completed only."""
    out = copy.deepcopy(seed)
    for m in out["matches"]:
        r = live.get(m["id"])
        if r and r.get("status") == "FT":
            m["result"] = {"home_goals": r["home_goals"], "away_goals": r["away_goals"]}
    return out
