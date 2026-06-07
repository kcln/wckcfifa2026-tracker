from src import predictor


def test_probs_sum_to_one_and_favor_stronger_team():
    p = predictor.predict(home_elo=2000, away_elo=1600, neutral=True)
    assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-9
    assert p["home"] > p["away"]


def test_home_advantage_applied_when_not_neutral():
    neutral = predictor.predict(home_elo=1700, away_elo=1700, neutral=True)
    hosted = predictor.predict(home_elo=1700, away_elo=1700, neutral=False)
    assert hosted["home"] > neutral["home"]


def test_expected_goals_positive():
    eg = predictor.expected_goals(home_elo=1800, away_elo=1500, neutral=True)
    assert eg["home"] > 0 and eg["away"] > 0


def test_elo_for_unknown_team_defaults_to_1500():
    assert predictor.elo_for("__nonexistent__") == 1500.0


def test_predict_teams_favors_known_stronger_team():
    # Spain is the strongest seed; Haiti is among the weakest. Spain should win.
    p = predictor.predict_teams("Spain", "Haiti", neutral=True)
    assert abs(p["home"] + p["draw"] + p["away"] - 1.0) < 1e-9
    assert p["home"] > p["away"]
