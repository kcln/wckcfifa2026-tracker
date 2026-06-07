import json
from pathlib import Path
from src import ml_predictor

def test_predict_match_returns_probs_for_known_pair():
    # uses the real committed predictions.json
    p = ml_predictor.predict_match("Spain", "Haiti")
    assert p is not None
    assert set(p) == {"home","draw","away"}
    assert abs(sum(p.values()) - 1.0) < 1e-6

def test_predict_match_returns_none_for_unknown_pair():
    assert ml_predictor.predict_match("__no__", "__such__") is None

def test_predict_match_returns_none_when_file_missing(tmp_path):
    missing = tmp_path / "nope.json"
    assert ml_predictor.predict_match("Spain", "Haiti", predictions_path=missing) is None

def test_match_prob_uses_ml_when_available():
    fallback = lambda h, a: {"home": 0.33, "draw": 0.34, "away": 0.33}
    fn = ml_predictor.match_prob_fn(fallback)
    out = fn("Spain", "Haiti")
    assert out != fallback("Spain", "Haiti")   # ML value, not fallback

def test_match_prob_uses_fallback_for_unknown_pair():
    fallback = lambda h, a: {"home": 0.33, "draw": 0.34, "away": 0.33}
    fn = ml_predictor.match_prob_fn(fallback)
    assert fn("__no__", "__such__") == {"home": 0.33, "draw": 0.34, "away": 0.33}
