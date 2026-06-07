"""Tiered fetch of live results, with cache fallback."""
from __future__ import annotations
import json
from pathlib import Path
import requests

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"


def parse_espn(payload: dict) -> dict:
    out = {}
    for ev in payload.get("events", []):
        if not ev.get("status", {}).get("type", {}).get("completed"):
            continue
        comp = ev["competitions"][0]["competitors"]
        h = next(c for c in comp if c["homeAway"] == "home")
        a = next(c for c in comp if c["homeAway"] == "away")
        out[ev["id"]] = {"home_goals": int(h["score"]), "away_goals": int(a["score"]), "status": "FT"}
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
