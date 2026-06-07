import numpy as np
from src import bracket_sim as bs


def test_group_table_orders_by_points_then_gd():
    matches = [
        {"home": "A", "away": "B", "result": {"home_goals": 3, "away_goals": 0}},
        {"home": "A", "away": "C", "result": {"home_goals": 1, "away_goals": 1}},
        {"home": "B", "away": "C", "result": {"home_goals": 0, "away_goals": 0}},
    ]
    table = bs.group_table(["A", "B", "C"], matches)
    assert table[0]["team"] == "A"
    assert [r["team"] for r in table] == ["A", "C", "B"]


def test_best_thirds_selects_n_by_points_then_gd():
    thirds = [
        {"team": "X", "points": 4, "gd": 1, "gf": 3},
        {"team": "Y", "points": 3, "gd": 2, "gf": 5},
        {"team": "Z", "points": 3, "gd": 1, "gf": 2},
    ]
    assert bs.best_thirds(thirds, n=2) == ["X", "Y"]


def test_unplayed_matches_dont_count_in_table():
    matches = [
        {"home": "A", "away": "B", "result": {"home_goals": 2, "away_goals": 0}},
        {"home": "A", "away": "C", "result": None},
    ]
    table = bs.group_table(["A", "B", "C"], matches)
    a = next(r for r in table if r["team"] == "A")
    assert a["played"] == 1 and a["points"] == 3


def test_title_odds_sum_to_one_on_real_fixtures():
    import json
    t = json.load(open("data/fixtures.json"))
    probs = lambda h, a: {"home": 0.4, "draw": 0.3, "away": 0.3}
    odds = bs.title_odds(t, match_prob=probs, iters=200)
    assert abs(sum(odds.values()) - 1.0) < 1e-6
    assert all(0.0 <= v <= 1.0 for v in odds.values())


def test_advancement_odds_keys_are_known_teams():
    import json
    t = json.load(open("data/fixtures.json"))
    probs = lambda h, a: {"home": 0.4, "draw": 0.3, "away": 0.3}
    adv = bs.advancement_odds(t, match_prob=probs, iters=100)
    all_teams = {x for g in t["groups"].values() for x in g}
    assert set(adv).issubset(all_teams)
    assert all(0.0 <= v <= 1.0 for v in adv.values())
