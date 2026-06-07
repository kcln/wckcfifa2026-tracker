# tests/test_state.py
from datetime import datetime, timezone
from src import state

def test_message_hash_is_stable_and_type_aware():
    a = state.message_hash("morning_brief", "2026-06-11", "body text")
    b = state.message_hash("morning_brief", "2026-06-11", "body text")
    c = state.message_hash("morning_brief", "2026-06-11", "different")
    assert a == b and a != c

def test_load_missing_returns_empty_skeleton(tmp_path):
    s = state.load(tmp_path / "state.json")
    assert s == {"days": [], "groups": {}, "bracket": {}, "season_ended": False}

def test_save_then_load_roundtrips(tmp_path):
    p = tmp_path / "state.json"
    data = {"days": [{"date": "2026-06-11"}], "groups": {}, "bracket": {}, "season_ended": False}
    state.save(p, data)
    assert state.load(p) == data

def test_today_pt_iso_format():
    fixed = datetime(2026, 6, 11, 6, 0, tzinfo=timezone.utc)  # 23:00 PT prev day
    assert state.today_pt_iso(now=fixed) == "2026-06-10"
