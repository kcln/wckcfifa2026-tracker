from src import fixtures


def test_seed_has_48_teams_in_12_groups():
    f = fixtures.load_seed()
    assert len(f["groups"]) == 12
    teams = [t for g in f["groups"].values() for t in g]
    assert len(teams) == 48 and len(set(teams)) == 48


def test_seed_has_104_matches():
    f = fixtures.load_seed()
    assert len(f["matches"]) == 104


def test_every_match_has_required_fields():
    for m in fixtures.load_seed()["matches"]:
        assert {"id", "date", "home", "away", "stage"} <= set(m)


def test_merge_results_locks_completed_matches():
    seed = {"matches": [{"id": "m1", "home": "USA", "away": "MEX", "result": None}]}
    live = {"m1": {"home_goals": 2, "away_goals": 1, "status": "FT"}}
    merged = fixtures.merge_results(seed, live)
    assert merged["matches"][0]["result"]["home_goals"] == 2
