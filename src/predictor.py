"""Elo + home-advantage heuristic: W/D/L probabilities and expected goals."""
from __future__ import annotations
import json
from pathlib import Path

HOME_ADV_ELO = 65.0   # added to home rating when not on neutral ground
DRAW_BASE = 0.27      # baseline draw mass for evenly matched sides
_ELO_PATH = Path(__file__).resolve().parent.parent / "data" / "elo_seed.json"


def _win_expectancy(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def predict(home_elo: float, away_elo: float, neutral: bool = True) -> dict:
    h = home_elo + (0.0 if neutral else HOME_ADV_ELO)
    we = _win_expectancy(h, away_elo)
    draw = DRAW_BASE * (1.0 - 2.0 * abs(we - 0.5))
    home = we - draw / 2.0
    away = (1.0 - we) - draw / 2.0
    total = home + draw + away
    return {"home": home / total, "draw": draw / total, "away": away / total}


def expected_goals(home_elo: float, away_elo: float, neutral: bool = True) -> dict:
    p = predict(home_elo, away_elo, neutral)
    base = 2.6
    return {"home": base * (p["home"] + p["draw"] / 2), "away": base * (p["away"] + p["draw"] / 2)}


def elo_for(team: str) -> float:
    """Look up a team's seed Elo; default 1500 if unknown. Bridges team names to predict()."""
    try:
        ratings = json.loads(_ELO_PATH.read_text())
    except Exception:
        return 1500.0
    return float(ratings.get(team, 1500.0))


def predict_teams(home: str, away: str, neutral: bool = True) -> dict:
    return predict(elo_for(home), elo_for(away), neutral)
