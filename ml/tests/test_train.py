import numpy as np, pandas as pd, json
from ml.src import train

def _synth(n=400, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        ed = rng.normal(0, 200)
        # stronger team (higher elo_diff) wins more often
        p_home = 1/(1+10**(-ed/400))
        r = rng.random()
        outcome = "home" if r < p_home*0.8 else ("draw" if r < p_home*0.8+0.2 else "away")
        rows.append({"elo_diff": ed, "form_home": rng.uniform(0,3),
                     "form_away": rng.uniform(0,3), "neutral": int(rng.random()<0.5),
                     "rest_home": rng.uniform(2,30), "rest_away": rng.uniform(2,30),
                     "outcome": outcome, "date": pd.Timestamp("2000-01-01")+pd.Timedelta(days=i)})
    return pd.DataFrame(rows)

def test_train_writes_model_and_metadata(tmp_path):
    df = _synth()
    clf = train.train(df, out_dir=tmp_path)
    assert (tmp_path / "model.pkl").exists()
    assert (tmp_path / "model.json").exists()
    meta = json.loads((tmp_path / "model.json").read_text())
    assert meta["n_rows"] == len(df)
    assert set(meta["classes"]) == {"home","draw","away"}
    assert meta["features"] == train.FEATURES

def test_model_probs_sum_to_one_over_three_classes(tmp_path):
    df = _synth()
    clf = train.train(df, out_dir=tmp_path)
    X = df[train.FEATURES].iloc[:5]
    proba = clf.predict_proba(X)
    assert proba.shape == (5, 3)
    assert np.allclose(proba.sum(axis=1), 1.0)

def test_model_ranks_strong_favorite_above_underdog(tmp_path):
    df = _synth(n=800)
    clf = train.train(df, out_dir=tmp_path)
    strong = pd.DataFrame([{"elo_diff": 400, "form_home": 2.5, "form_away": 1.0,
                            "neutral": 1, "rest_home": 5.0, "rest_away": 5.0}])
    weak   = pd.DataFrame([{"elo_diff": -400, "form_home": 1.0, "form_away": 2.5,
                            "neutral": 1, "rest_home": 5.0, "rest_away": 5.0}])
    classes = list(clf.classes_)
    hi = classes.index("home")
    assert clf.predict_proba(strong)[0][hi] > clf.predict_proba(weak)[0][hi]
