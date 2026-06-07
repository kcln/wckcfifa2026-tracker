"""Bridge to the ml/ engine. Every public fn catches all and returns None on
failure so the live tracker never depends on ML for correctness (v1: always None
because ml/ does not exist yet; activated in a later task)."""
from __future__ import annotations


def predict_match(home: str, away: str) -> dict | None:
    try:
        import sys, pathlib
        root = pathlib.Path(__file__).resolve().parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from ml.src.predict import predict_wdl   # exists only after the ML engine is built
        return predict_wdl(home, away)
    except Exception:
        return None


def match_prob_fn(fallback):
    """Return f(home, away)->probs using ML when available, else fallback."""
    def _f(home, away):
        return predict_match(home, away) or fallback(home, away)
    return _f
