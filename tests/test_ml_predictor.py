from src import ml_predictor

def test_bridge_returns_none_when_ml_absent():
    assert ml_predictor.predict_match("USA", "Mexico") is None

def test_match_prob_uses_fallback_when_ml_none():
    fallback = lambda h, a: {"home": 0.5, "draw": 0.3, "away": 0.2}
    fn = ml_predictor.match_prob_fn(fallback)
    assert fn("USA", "Mexico") == {"home": 0.5, "draw": 0.3, "away": 0.2}
