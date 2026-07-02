"""This tournament's played matches as training rows.

Bridges the live tracker's persisted results (``state.json``) into the exact
schema of the historical results CSV, so the nightly retrain can append them
and the feature pass treats World Cup 2026 like any other stretch of history:
Elo moves with every result, form windows include tournament games, and rest
days reflect the compressed schedule.

Knockout fixtures carry slot tokens ("2A", "W73") in the seed; they are
resolved to real team names with the same ``src.knockout.resolve_bracket``
logic the live site uses. ``neutral`` is TRUE-home aware: a host (Mexico/USA/
Canada) playing inside its own country is a home side, everyone else is
neutral — matching how the historical dataset encodes it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import bracket_sim, fixtures, knockout  # noqa: E402

STATE_PATH = REPO_ROOT / "state.json"

# Venue -> (city, country) in the historical dataset's vocabulary.
_VENUES = {
    "Atlanta": ("Atlanta", "United States"),
    "Boston (Foxborough)": ("Foxborough", "United States"),
    "Dallas (Arlington)": ("Arlington", "United States"),
    "Guadalajara (Zapopan)": ("Zapopan", "Mexico"),
    "Houston": ("Houston", "United States"),
    "Kansas City": ("Kansas City", "United States"),
    "Los Angeles (Inglewood)": ("Inglewood", "United States"),
    "Mexico City": ("Mexico City", "Mexico"),
    "Miami (Miami Gardens)": ("Miami Gardens", "United States"),
    "Monterrey (Guadalupe)": ("Guadalupe", "Mexico"),
    "New York/New Jersey (East Rutherford)": ("East Rutherford", "United States"),
    "Philadelphia": ("Philadelphia", "United States"),
    "San Francisco Bay Area (Santa Clara)": ("Santa Clara", "United States"),
    "Seattle": ("Seattle", "United States"),
    "Toronto": ("Toronto", "Canada"),
    "Vancouver": ("Vancouver", "Canada"),
}

# Host team -> the country name it is "at home" in.
_HOST_COUNTRY = {"Mexico": "Mexico", "USA": "United States", "Canada": "Canada"}


def _group_tables(merged: dict) -> dict:
    """Current group tables {letter: rows}, same math as the live tracker."""
    by_group: dict = {g: [] for g in merged["groups"]}
    for m in merged["matches"]:
        if m["stage"] == "group" and m.get("group") in by_group:
            by_group[m["group"]].append(m)
    return {g: bracket_sim.group_table(merged["groups"][g], by_group[g])
            for g in merged["groups"]}


def tournament_frame(state_path: Path | str = STATE_PATH) -> pd.DataFrame:
    """Every played tournament match as a historical-schema DataFrame:
    date, home_team, away_team, home_score, away_score, neutral, tournament,
    city, country. Knockout slot tokens are resolved to real teams; matches
    whose teams can't be resolved yet are skipped."""
    state = json.loads(Path(state_path).read_text())
    results = state.get("results") or {}
    seed = fixtures.load_seed()
    merged = fixtures.merge_results(
        seed, {mid: {**r, "status": "FT"} for mid, r in results.items()})
    resolved = knockout.resolve_bracket(
        merged["matches"], _group_tables(merged), results)

    rows = []
    for m in merged["matches"]:
        r = m.get("result")
        if not r:
            continue
        home, away = resolved.get(str(m["id"]), (m["home"], m["away"]))
        if knockout.is_descriptor(home) or knockout.is_descriptor(away):
            continue                     # not yet resolvable — skip, next run
        city, country = _VENUES.get(m.get("venue", ""), ("", ""))
        rows.append({
            "date": pd.Timestamp(m["date"]),
            "home_team": home,
            "away_team": away,
            "home_score": int(r["home_goals"]),
            "away_score": int(r["away_goals"]),
            "neutral": _HOST_COUNTRY.get(home) != country,
            "tournament": "FIFA World Cup",
            "city": city,
            "country": country,
        })
    return pd.DataFrame(rows)


def next_fixture_dates(state_path: Path | str = STATE_PATH) -> dict:
    """Team -> ISO date of its next known (unplayed, team-resolved) fixture,
    from the live bracket. Drives rest-days at prediction time."""
    state = json.loads(Path(state_path).read_text())
    results = state.get("results") or {}
    seed = fixtures.load_seed()
    merged = fixtures.merge_results(
        seed, {mid: {**r, "status": "FT"} for mid, r in results.items()})
    resolved = knockout.resolve_bracket(
        merged["matches"], _group_tables(merged), results)

    nxt: dict = {}
    for m in sorted(merged["matches"], key=lambda x: x.get("date") or ""):
        if m.get("result"):
            continue
        home, away = resolved.get(str(m["id"]), (m["home"], m["away"]))
        for team in (home, away):
            if not knockout.is_descriptor(team) and team not in nxt:
                nxt[team] = m.get("date")
    return nxt
