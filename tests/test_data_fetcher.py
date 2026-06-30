from datetime import datetime
from zoneinfo import ZoneInfo

from src import data_fetcher as df


def test_scoreboard_urls_span_pt_day_boundary():
    # A 9pm PT kickoff is 04:00 UTC the next day, so covering a PT day needs
    # both the current and adjacent UTC date buckets, not just the default feed.
    now = datetime(2026, 6, 17, 6, 0, tzinfo=ZoneInfo("UTC"))
    urls = df._scoreboard_urls(now)
    assert df.ESPN_URL in urls
    assert any("dates=20260616" in u for u in urls)
    assert any("dates=20260617" in u for u in urls)
    assert any("dates=20260618" in u for u in urls)


def test_merge_events_dedups_by_id_across_payloads():
    # The late match (id 4) appears only in the explicit date bucket, not the
    # default feed; the merge must surface it. Shared ids dedup (later wins).
    default = {"events": [{"id": "1"}, {"id": "2"}]}
    bucket = {"events": [{"id": "2"}, {"id": "4"}]}
    merged = df._merge_events([default, bucket])
    ids = sorted(e["id"] for e in merged["events"])
    assert ids == ["1", "2", "4"]


def test_parse_espn_scoreboard_extracts_completed_results():
    sample = {"events": [{"id": "401", "date": "2026-06-11T19:00Z",
        "status": {"type": {"completed": True}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "2", "team": {"displayName": "Mexico"}},
            {"homeAway": "away", "score": "1", "team": {"displayName": "South Africa"}}]}]}]}
    out = df.parse_espn(sample)
    assert out["401"] == {"home": "Mexico", "away": "South Africa",
        "date": "2026-06-11", "home_goals": 2, "away_goals": 1,
        "status": "FT", "clock": "", "events": []}


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


# Real ESPN scoreboard shape: competition.details carries goals + cards.
def _sample_with_details():
    return {"events": [{"id": "500", "date": "2026-06-13T19:00Z",
        "status": {"type": {"completed": True}},
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "score": "1", "team": {"id": "BRA", "displayName": "Brazil"}},
                {"homeAway": "away", "score": "1", "team": {"id": "MAR", "displayName": "Morocco"}}],
            "details": [
                {"type": {"text": "Goal"}, "scoringPlay": True, "redCard": False,
                 "yellowCard": False, "ownGoal": False, "penaltyKick": False,
                 "team": {"id": "MAR"}, "clock": {"displayValue": "21'"},
                 "athletesInvolved": [{"displayName": "Ismael Saibari"}]},
                {"type": {"text": "Yellow Card"}, "scoringPlay": False,
                 "redCard": False, "yellowCard": True, "team": {"id": "BRA"},
                 "clock": {"displayValue": "37'"},
                 "athletesInvolved": [{"displayName": "Casemiro"}]},
                {"type": {"text": "Goal - Penalty"}, "scoringPlay": True,
                 "redCard": False, "yellowCard": False, "penaltyKick": True,
                 "team": {"id": "BRA"}, "clock": {"displayValue": "64'"},
                 "athletesInvolved": [{"displayName": "Vinicius Jr"}]},
                {"type": {"text": "Red Card"}, "scoringPlay": False,
                 "redCard": True, "yellowCard": False, "team": {"id": "BRA"},
                 "clock": {"displayValue": "80'"},
                 "athletesInvolved": [{"displayName": "Gabriel"}]}]}]}]}


def test_parse_espn_extracts_goals_and_red_cards():
    out = df.parse_espn(_sample_with_details())
    evs = out["500"]["events"]
    # goal, penalty goal, red card — yellow card is dropped
    kinds = [e["kind"] for e in evs]
    assert kinds == ["goal", "penalty", "red"]
    assert evs[0] == {"kind": "goal", "player": "Ismael Saibari",
                      "team": "Morocco", "minute": "21'"}
    assert evs[1]["kind"] == "penalty" and evs[1]["team"] == "Brazil"
    assert evs[2] == {"kind": "red", "player": "Gabriel",
                      "team": "Brazil", "minute": "80'"}


def test_parse_espn_skips_shootout_events():
    sample = _sample_with_details()
    sample["events"][0]["competitions"][0]["details"][0]["shootout"] = True
    out = df.parse_espn(sample)
    assert [e["kind"] for e in out["500"]["events"]] == ["penalty", "red"]


def test_parse_espn_captures_live_in_progress_with_clock():
    sample = {"events": [{"id": "700", "date": "2026-06-16T19:00Z",
        "status": {"displayClock": "50'",
                   "type": {"completed": False, "state": "in",
                            "name": "STATUS_SECOND_HALF"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "1", "team": {"displayName": "Argentina"}},
            {"homeAway": "away", "score": "0", "team": {"displayName": "Algeria"}}]}]}]}
    out = df.parse_espn(sample)
    assert out["700"]["status"] == "LIVE"
    assert out["700"]["clock"] == "50'"
    assert out["700"]["home_goals"] == 1 and out["700"]["away_goals"] == 0


def test_parse_espn_captures_penalty_winner_and_tally():
    sample = {"events": [{"id": "74", "date": "2026-06-29T20:30Z",
        "status": {"type": {"completed": True, "name": "STATUS_FINAL_PEN"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "1", "winner": False, "shootoutScore": 3,
             "team": {"displayName": "Germany"}},
            {"homeAway": "away", "score": "1", "winner": True, "shootoutScore": 4,
             "team": {"displayName": "Paraguay"}}]}]}]}
    e = df.parse_espn(sample)["74"]
    assert e["home_goals"] == 1 and e["away_goals"] == 1
    assert e["winner"] == "Paraguay"
    assert e["home_pens"] == 3 and e["away_pens"] == 4
