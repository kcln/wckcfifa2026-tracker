"""Inference layer for the 3-class match-outcome model.

The model predicts from *pre-tournament* team state (final Elo + final recent
form derived from the same chronological pass that trained it), so every
``(home, away)`` pairing has a STATIC probability across the tournament. We
exploit that here in two ways:

  1. ``predict_wdl`` is ``lru_cache``-d, so the bracket Monte Carlo (which
     replays the same pairings thousands of times) pays the model cost once per
     unique pairing.
  2. ``export_predictions`` precomputes every ordered pairing of the 48 World
     Cup teams into ``predictions.json``. The lean live runtime (stdlib +
     requests + numpy only — NO pandas/sklearn/lightgbm) reads that JSON
     directly, so production never imports the heavy ML stack.

``team_state.json`` MUST be derived from ``features.build`` over the full
historical dataset (same Elo/form pass as training) so the inference
``elo_diff`` lands on exactly the scale the model trained on.
"""
from __future__ import annotations

import functools
import json
import pickle
from pathlib import Path

import numpy as np

from ml.src.train import FEATURES

# <repo>/ml/data/models  (this file lives at <repo>/ml/src/predict.py)
DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "data" / "models"
MODEL_PATH = DEFAULT_MODEL_DIR / "model.pkl"
TEAM_STATE_PATH = DEFAULT_MODEL_DIR / "team_state.json"
PREDICTIONS_PATH = DEFAULT_MODEL_DIR / "predictions.json"

# Defaults for teams absent from the historical state table.
DEFAULT_ELO = 1500.0
DEFAULT_FORM = 1.5


@functools.lru_cache(maxsize=None)
def _model():
    """Lazily load and cache the calibrated estimator from model.pkl."""
    with open(MODEL_PATH, "rb") as fh:
        return pickle.load(fh)


@functools.lru_cache(maxsize=None)
def _team_state() -> dict:
    """Lazily load and cache the team -> {elo, form} table from team_state.json."""
    return json.loads(Path(TEAM_STATE_PATH).read_text())


def build_team_state(out_path: Path | str = TEAM_STATE_PATH) -> dict:
    """Build team -> {elo, form} from the training-consistent features pass.

    Runs ingest + features.build over the real historical data, then for each
    team takes its FINAL Elo and FINAL recent form (last-5 ppg) as of the most
    recent match it appears in. Writes the table to ``out_path`` and returns it.

    Done this way (not via a separate Elo recompute) so inference state matches
    the running state the model saw at train time.
    """
    from ml.src import ingest, features

    raw = ingest.load_results()
    feat = features.build(raw)
    ordered = feat.sort_values("date", kind="stable").reset_index(drop=True)

    # Walk chronologically; each row carries the PRE-match state, so the latest
    # row a team appears in (as home or away) holds its most-recent known state.
    state: dict[str, dict] = {}
    for row in ordered.itertuples(index=False):
        state[row.home_team] = {"elo": float(row.elo_home), "form": float(row.form_home)}
        state[row.away_team] = {"elo": float(row.elo_away), "form": float(row.form_away)}

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(state, indent=2, sort_keys=True))

    # Refresh the memoized cache if we just rewrote the default artifact.
    if out_path == Path(TEAM_STATE_PATH):
        _team_state.cache_clear()
    return state


@functools.lru_cache(maxsize=None)
def predict_wdl(home: str, away: str, neutral: bool = True) -> dict:
    """Return calibrated {home, draw, away} probabilities for a pairing.

    Looks up each team's Elo + form (defaulting unknown teams to
    DEFAULT_ELO/DEFAULT_FORM), assembles the FEATURES row as a plain numpy array
    (no pandas at inference), and maps predict_proba columns through
    ``model.classes_``. lru_cached so repeated pairings are free under the
    bracket Monte Carlo.
    """
    state = _team_state()
    hs = state.get(home, {})
    as_ = state.get(away, {})

    elo_home = float(hs.get("elo", DEFAULT_ELO))
    elo_away = float(as_.get("elo", DEFAULT_ELO))
    form_home = float(hs.get("form", DEFAULT_FORM))
    form_away = float(as_.get("form", DEFAULT_FORM))

    feats = {
        "elo_diff": elo_home - elo_away,
        "form_home": form_home,
        "form_away": form_away,
        "neutral": int(neutral),
    }
    X = np.array([[feats[name] for name in FEATURES]], dtype=float)

    model = _model()
    proba = model.predict_proba(X)[0]
    by_class = {str(cls): float(p) for cls, p in zip(model.classes_, proba)}
    return {
        "home": by_class.get("home", 0.0),
        "draw": by_class.get("draw", 0.0),
        "away": by_class.get("away", 0.0),
    }


def export_predictions(
    teams: list[str], out_path: Path | str = PREDICTIONS_PATH, neutral: bool = True
) -> dict:
    """Precompute every ordered pairing into a ``{"home|away": {...}}`` lookup.

    Writes the lookup to ``out_path`` and returns it. For n teams this is
    n*(n-1) entries (ordered pairs, no self-pairs).
    """
    lookup: dict[str, dict] = {}
    for home in teams:
        for away in teams:
            if home == away:
                continue
            lookup[f"{home}|{away}"] = predict_wdl(home, away, neutral)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(lookup, indent=2, sort_keys=True))
    return lookup


def _world_cup_teams() -> list[str]:
    """Load the 48 World Cup teams from the live fixtures groups."""
    fixtures_path = Path(__file__).resolve().parents[2] / "data" / "fixtures.json"
    groups = json.loads(fixtures_path.read_text())["groups"]
    teams: list[str] = []
    for members in groups.values():
        teams.extend(members)
    return teams


if __name__ == "__main__":
    build_team_state()
    teams = _world_cup_teams()
    lookup = export_predictions(teams)
    print(f"teams: {len(teams)}")
    print(f"predictions.json entries: {len(lookup)}  (expected {len(teams) * (len(teams) - 1)})")
    for h, a in [("Spain", "Haiti"), ("Brazil", "Argentina")]:
        p = predict_wdl(h, a)
        print(f"  {h} vs {a}: home={p['home']:.3f} draw={p['draw']:.3f} away={p['away']:.3f}")
