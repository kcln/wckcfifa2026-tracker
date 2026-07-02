import json
import pandas as pd
from ml.src import tournament


def test_tournament_frame_matches_historical_schema(tmp_path):
    frame = tournament.tournament_frame()   # real state.json in the repo
    if frame.empty:
        return                              # pre-tournament: nothing to assert
    assert list(frame.columns) == ["date", "home_team", "away_team",
                                   "home_score", "away_score", "neutral",
                                   "tournament", "city", "country"]
    # no unresolved slot tokens ever leak into training rows
    assert not frame["home_team"].str.contains(r"^\d|^W\d|^L\d|/").any()
    assert not frame["away_team"].str.contains(r"^\d|^W\d|^L\d|/").any()
    # hosts at home are non-neutral, everyone else neutral
    mex = frame[(frame.home_team == "Mexico") & (frame.country == "Mexico")]
    if len(mex):
        assert not mex["neutral"].any()
    non_host = frame[~frame.home_team.isin(["Mexico", "USA", "Canada"])]
    assert non_host["neutral"].all()


def test_next_fixture_dates_only_real_teams():
    nxt = tournament.next_fixture_dates()
    from src import knockout
    assert all(not knockout.is_descriptor(t) for t in nxt)
    assert all(isinstance(d, str) and d.startswith("2026-") for d in nxt.values())
