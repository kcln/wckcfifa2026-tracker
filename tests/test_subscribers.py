import json

from src import subscribers as sub


def test_load_seeds_from_secret_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_IDS", "111,222")
    d = sub.load(tmp_path / "subscribers.json")
    assert d["approved"] == ["111", "222"]
    assert d["onboarded"] == ["111", "222"]   # existing subs skip onboarding
    assert d["pending"] == {} and d["last_update_id"] == 0


def test_load_existing_file_fills_defaults(tmp_path):
    p = tmp_path / "subscribers.json"
    p.write_text(json.dumps({"approved": ["1"]}))
    d = sub.load(p)
    assert d["approved"] == ["1"]
    assert d["pending"] == {} and d["onboarded"] == [] \
        and d["last_update_id"] == 0


def test_save_round_trips(tmp_path):
    p = tmp_path / "subscribers.json"
    data = {"approved": ["1", "2"], "pending": {"3": {"ts": "T"}},
            "onboarded": ["1"], "last_update_id": 42}
    sub.save(p, data)
    assert sub.load(p) == data
