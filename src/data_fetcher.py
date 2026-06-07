"""Tiered fetch of live results, with cache fallback."""
from __future__ import annotations
import json
from pathlib import Path
import requests

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"


def _team_name(competitor: dict) -> str:
    """Pull a display name from an ESPN competitor, tolerant of payload shape."""
    team = competitor.get("team", {})
    return team.get("displayName") or team.get("name") or competitor.get("name", "")


def parse_espn(payload: dict) -> dict:
    """Extract completed results from an ESPN scoreboard payload.

    Each entry carries the team names and match date in addition to the score, so
    the tracker can reconcile feed events to our seed fixtures by (home, away, date)
    — ESPN's event ids do not match our seed ids.
    """
    out = {}
    for ev in payload.get("events", []):
        if not ev.get("status", {}).get("type", {}).get("completed"):
            continue
        comp = ev["competitions"][0]["competitors"]
        h = next(c for c in comp if c["homeAway"] == "home")
        a = next(c for c in comp if c["homeAway"] == "away")
        out[ev["id"]] = {
            "home": _team_name(h),
            "away": _team_name(a),
            "date": (ev.get("date") or "")[:10],  # ISO timestamp -> YYYY-MM-DD
            "home_goals": int(h["score"]),
            "away_goals": int(a["score"]),
            "status": "FT",
        }
    return out


def _espn_source() -> dict:
    return parse_espn(requests.get(ESPN_URL, timeout=15).json())


def fetch_results(sources=None, cache_path: Path | None = None) -> dict:
    sources = sources if sources is not None else [_espn_source]
    for src in sources:
        try:
            data = src()
            if cache_path is not None and data:
                Path(cache_path).write_text(json.dumps(data))
            return data
        except Exception:
            continue
    if cache_path and Path(cache_path).exists():
        return json.loads(Path(cache_path).read_text())
    return {}
