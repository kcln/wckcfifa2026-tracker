"""Bridge to the ml/ engine. Reads precomputed win/draw/loss probabilities from
ml/data/models/predictions.json using the standard library only (no sklearn /
lightgbm in the live runtime). Every public fn catches all and returns None on
failure so the live tracker silently degrades to the Elo fallback and is never
broken by a missing/corrupt predictions file or an unknown team pairing."""
from __future__ import annotations

import json
from pathlib import Path

PREDICTIONS_PATH = Path(__file__).resolve().parents[1] / "ml" / "data" / "models" / "predictions.json"

# Module-level cache of loaded prediction files, keyed by resolved path string.
# Caches the FILE load (not per-pair results) so the bracket Monte Carlo does
# not re-read disk on every match lookup.
_CACHE: dict[str, dict] = {}


def _load(predictions_path: Path) -> dict:
    key = str(Path(predictions_path).resolve())
    cached = _CACHE.get(key)
    if cached is None:
        with open(predictions_path, encoding="utf-8") as fh:
            cached = json.load(fh)
        _CACHE[key] = cached
    return cached


def predict_match(home: str, away: str, predictions_path: Path | None = None) -> dict | None:
    """Return {'home','draw','away'} probs for the pairing, or None on any failure
    (missing file, bad json, unknown pairing). predictions_path is injectable;
    when omitted it reads the module-level PREDICTIONS_PATH at call time so tests
    can monkeypatch it."""
    try:
        if predictions_path is None:
            predictions_path = PREDICTIONS_PATH
        data = _load(predictions_path)
        return data[f"{home}|{away}"]
    except Exception:
        return None


def match_prob_fn(fallback):
    """Return f(home, away)->probs using ML when available, else fallback."""
    def _f(home, away):
        return predict_match(home, away) or fallback(home, away)
    return _f
