from src import data_fetcher as df


def test_parse_espn_scoreboard_extracts_completed_results():
    sample = {"events": [{"id": "401", "date": "2026-06-11T19:00Z",
        "status": {"type": {"completed": True}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "2", "team": {"displayName": "Mexico"}},
            {"homeAway": "away", "score": "1", "team": {"displayName": "South Africa"}}]}]}]}
    out = df.parse_espn(sample)
    assert out["401"] == {"home": "Mexico", "away": "South Africa",
        "date": "2026-06-11", "home_goals": 2, "away_goals": 1, "status": "FT"}


def test_parse_espn_skips_incomplete_events():
    sample = {"events": [{"id": "402", "date": "2026-06-11T22:00Z",
        "status": {"type": {"completed": False}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "0", "team": {"displayName": "USA"}},
            {"homeAway": "away", "score": "0", "team": {"displayName": "Canada"}}]}]}]}
    assert df.parse_espn(sample) == {}


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


def test_parse_espn_emits_half_time_scores():
    sample = {"events": [{"id": "403", "date": "2026-06-11T19:00Z",
        "status": {"type": {"completed": False, "name": "STATUS_HALFTIME"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "1", "team": {"displayName": "Mexico"}},
            {"homeAway": "away", "score": "0", "team": {"displayName": "South Africa"}}]}]}]}
    out = df.parse_espn(sample)
    assert out["403"]["status"] == "HT"
    assert out["403"]["home_goals"] == 1 and out["403"]["away_goals"] == 0


def test_parse_espn_still_skips_first_half_in_progress():
    sample = {"events": [{"id": "404", "date": "2026-06-11T19:00Z",
        "status": {"type": {"completed": False, "name": "STATUS_FIRST_HALF"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "1", "team": {"displayName": "USA"}},
            {"homeAway": "away", "score": "0", "team": {"displayName": "Canada"}}]}]}]}
    assert df.parse_espn(sample) == {}


def test_parse_espn_converts_utc_date_to_pt_date():
    # Tonight's bug: South Korea vs Czechia kicked off 2026-06-12T02:00 UTC,
    # which is 2026-06-11 19:00 PT. Seed fixture dates are PT, so the feed
    # entry must carry the PT date or reconcile_results silently drops it.
    sample = {"events": [{"id": "405", "date": "2026-06-12T02:00Z",
        "status": {"type": {"completed": True}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "2", "team": {"displayName": "South Korea"}},
            {"homeAway": "away", "score": "1", "team": {"displayName": "Czechia"}}]}]}]}
    out = df.parse_espn(sample)
    assert out["405"]["date"] == "2026-06-11"


def test_parse_espn_halftime_also_uses_pt_date():
    sample = {"events": [{"id": "406", "date": "2026-06-12T02:00Z",
        "status": {"type": {"completed": False, "name": "STATUS_HALFTIME"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "1", "team": {"displayName": "South Korea"}},
            {"homeAway": "away", "score": "0", "team": {"displayName": "Czechia"}}]}]}]}
    out = df.parse_espn(sample)
    assert out["406"]["date"] == "2026-06-11"
    assert out["406"]["status"] == "HT"
