from pathlib import Path
from src import tracker, ml_predictor

def test_tracker_run_succeeds_with_ml_active(tmp_path):
    cfg = tracker.Config(
        state_path=tmp_path/"s.json", html_path=tmp_path/"i.html",
        cache_path=tmp_path/"c.json", token="", chat_ids=[],
        fetch=lambda: {}, sender=lambda t, **k: True,
        now_iso="2026-06-11", sim_iters=50)
    assert tracker.run(cfg) == 0

def test_match_prob_fallback_when_predictions_corrupt(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")
    monkeypatch.setattr(ml_predictor, "PREDICTIONS_PATH", bad)
    # clear any memoized load
    if hasattr(ml_predictor, "_CACHE"):
        ml_predictor._CACHE.clear()
    fallback = lambda h, a: {"home": 0.5, "draw": 0.3, "away": 0.2}
    fn = ml_predictor.match_prob_fn(fallback)
    assert fn("Spain", "Haiti") == {"home": 0.5, "draw": 0.3, "away": 0.2}
