from src import data_fetcher as df


def test_parse_espn_scoreboard_extracts_completed_results():
    sample = {"events": [{"id": "1", "status": {"type": {"completed": True}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "2"}, {"homeAway": "away", "score": "1"}]}]}]}
    out = df.parse_espn(sample)
    assert out["1"] == {"home_goals": 2, "away_goals": 1, "status": "FT"}


def test_fetch_results_falls_back_to_cache_on_total_failure(tmp_path):
    cache = tmp_path / "cache.json"
    cache.write_text('{"1": {"home_goals": 3, "away_goals": 0, "status": "FT"}}')
    out = df.fetch_results(sources=[lambda: (_ for _ in ()).throw(RuntimeError())],
                           cache_path=cache)
    assert out["1"]["home_goals"] == 3


def test_fetch_results_writes_cache_on_success(tmp_path):
    cache = tmp_path / "cache.json"
    good = {"1": {"home_goals": 1, "away_goals": 1, "status": "FT"}}
    out = df.fetch_results(sources=[lambda: good], cache_path=cache)
    assert out == good and cache.exists()
