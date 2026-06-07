import json, numpy as np
from ml.src import predict

def test_predict_wdl_sums_to_one_and_has_three_keys():
    p = predict.predict_wdl("Spain", "Haiti")
    assert set(p) == {"home","draw","away"}
    assert abs(sum(p.values()) - 1.0) < 1e-6

def test_predict_wdl_favours_strong_over_weak():
    strong = predict.predict_wdl("Spain", "Haiti")     # strong home
    weak = predict.predict_wdl("Haiti", "Spain")       # weak home
    assert strong["home"] > weak["home"]

def test_unknown_team_defaults_do_not_crash():
    p = predict.predict_wdl("__nowhere__", "__noland__")
    assert abs(sum(p.values()) - 1.0) < 1e-6

def test_export_predictions_writes_lookup(tmp_path):
    out = tmp_path / "predictions.json"
    d = predict.export_predictions(["Spain","Haiti","Brazil"], out_path=out)
    assert out.exists()
    data = json.loads(out.read_text())
    assert "Spain|Haiti" in data and abs(sum(data["Spain|Haiti"].values())-1.0) < 1e-6
    # ordered pairs, no self-pairs: 3 teams -> 6 entries
    assert len(data) == 6
