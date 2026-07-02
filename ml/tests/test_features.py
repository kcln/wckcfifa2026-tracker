import pandas as pd
from ml.src import features

def _df(rows):
    return pd.DataFrame(rows)

def test_first_match_has_zero_form_and_equal_elo():
    df = _df([
        {"date": pd.Timestamp("2000-01-01"), "home_team":"A","away_team":"B",
         "home_score":1,"away_score":0,"neutral":False},
    ])
    feat = features.build(df)
    row = feat.iloc[0]
    assert row["form_home"] == 0 and row["form_away"] == 0
    assert row["elo_diff"] == 0          # both start at 1500 before any match
    assert row["outcome"] == "home"

def test_no_leakage_elo_updates_only_after_match():
    # A beats B, then they rematch; in match 2, A's pre-match elo must exceed B's
    df = _df([
        {"date": pd.Timestamp("2000-01-01"),"home_team":"A","away_team":"B","home_score":3,"away_score":0,"neutral":True},
        {"date": pd.Timestamp("2000-02-01"),"home_team":"A","away_team":"B","home_score":0,"away_score":0,"neutral":True},
    ])
    feat = features.build(df)
    assert feat.iloc[0]["elo_diff"] == 0          # before any result
    assert feat.iloc[1]["elo_diff"] > 0           # A rated higher after winning match 1
    assert feat.iloc[1]["outcome"] == "draw"

def test_form_reflects_only_prior_matches():
    df = _df([
        {"date": pd.Timestamp("2000-01-01"),"home_team":"A","away_team":"B","home_score":2,"away_score":0,"neutral":True},
        {"date": pd.Timestamp("2000-01-02"),"home_team":"A","away_team":"C","home_score":1,"away_score":0,"neutral":True},
        {"date": pd.Timestamp("2000-01-03"),"home_team":"A","away_team":"D","home_score":0,"away_score":1,"neutral":True},
    ])
    feat = features.build(df)
    # before match 3, A has won 2 → form = 3.0 (ppg over 2 games)
    assert abs(feat.iloc[2]["form_home"] - 3.0) < 1e-9

def test_build_is_sorted_by_date_and_outputs_expected_columns():
    df = _df([
        {"date": pd.Timestamp("2001-01-01"),"home_team":"X","away_team":"Y","home_score":1,"away_score":1,"neutral":False},
        {"date": pd.Timestamp("2000-01-01"),"home_team":"X","away_team":"Y","home_score":1,"away_score":0,"neutral":False},
    ])
    feat = features.build(df)
    assert list(feat["date"]) == sorted(feat["date"])
    for col in ["elo_home","elo_away","elo_diff","form_home","form_away","neutral","outcome"]:
        assert col in feat.columns


def test_rest_days_computed_pit_safe():
    import pandas as pd
    from ml.src import features
    df = pd.DataFrame([
        {"date": pd.Timestamp("2026-06-01"), "home_team": "A", "away_team": "B",
         "home_score": 1, "away_score": 0, "neutral": True},
        {"date": pd.Timestamp("2026-06-05"), "home_team": "A", "away_team": "C",
         "home_score": 2, "away_score": 0, "neutral": True},
    ])
    feat = features.build(df)
    assert feat.iloc[0]["rest_home"] == features.REST_CAP   # debut -> cap
    assert feat.iloc[1]["rest_home"] == 4.0                 # played 4 days ago
    assert feat.iloc[1]["rest_away"] == features.REST_CAP   # C's debut


def test_build_return_state_includes_newest_result():
    import pandas as pd
    from ml.src import features
    df = pd.DataFrame([
        {"date": pd.Timestamp("2026-06-01"), "home_team": "A", "away_team": "B",
         "home_score": 3, "away_score": 0, "neutral": True},
    ])
    frame, state = features.build(df, return_state=True)
    assert state["elo"]["A"] > features.START_ELO            # win already counted
    assert state["elo"]["B"] < features.START_ELO
    assert state["form"]["A"] == 3.0
    assert str(state["last_played"]["A"].date()) == "2026-06-01"
