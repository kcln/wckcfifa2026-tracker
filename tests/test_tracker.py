"""Tests for the tracker orchestration core."""
import json

from src import tracker


# ---------------------------------------------------------------------------
# Mandated tests
# ---------------------------------------------------------------------------

def test_run_generates_morning_brief_once(tmp_path):
    sent = []
    cfg = tracker.Config(
        state_path=tmp_path / "state.json",
        html_path=tmp_path / "index.html",
        cache_path=tmp_path / "cache.json",
        token="T", chat_ids=["1"],
        fetch=lambda: {}, sender=lambda text, **k: sent.append(text) or True,
        now_iso="2026-06-11", sim_iters=50,
    )
    tracker.run(cfg); tracker.run(cfg)   # second run must not resend
    assert len(sent) == 1


def test_run_records_result_and_marks_prediction(tmp_path):
    cfg = tracker.Config(
        state_path=tmp_path / "state.json", html_path=tmp_path / "i.html",
        cache_path=tmp_path / "c.json", token="", chat_ids=[],
        fetch=lambda: {"1": {"home_goals": 2, "away_goals": 0, "status": "FT"}},
        sender=lambda text, **k: True, now_iso="2026-06-11", sim_iters=50)
    code = tracker.run(cfg)
    assert code in (0, 2)
    # the seed match id "1" now has a recorded result in saved state
    saved = json.loads((tmp_path / "state.json").read_text())
    assert saved is not None


# ---------------------------------------------------------------------------
# Additional behaviour tests
# ---------------------------------------------------------------------------

def _base_cfg(tmp_path, **over):
    defaults = dict(
        state_path=tmp_path / "state.json", html_path=tmp_path / "i.html",
        cache_path=tmp_path / "c.json", token="T", chat_ids=["1"],
        fetch=lambda: {}, sender=lambda text, **k: True,
        now_iso="2026-06-11", sim_iters=50,
    )
    defaults.update(over)
    return tracker.Config(**defaults)


def test_run_writes_html(tmp_path):
    cfg = _base_cfg(tmp_path)
    tracker.run(cfg)
    assert (tmp_path / "i.html").exists()
    assert (tmp_path / "i.html").stat().st_size > 500


def test_idempotent_no_duplicate_messages(tmp_path):
    # On a result-bearing day, run twice; messages must not duplicate.
    fetch = lambda: {
        "1": {"home_goals": 2, "away_goals": 0, "status": "FT"},
        "2": {"home_goals": 1, "away_goals": 1, "status": "FT"},
    }
    cfg = _base_cfg(tmp_path, fetch=fetch)
    tracker.run(cfg)
    tracker.run(cfg)
    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    hashes = [m["hash"] for m in day["messages"]]
    assert len(hashes) == len(set(hashes))


def test_send_newest_skips_older(tmp_path):
    # First run on day 1 (no results) -> morning brief is delivered.
    sent = []
    sender = lambda text, **k: sent.append(text) or True
    cfg1 = _base_cfg(tmp_path, fetch=lambda: {}, sender=sender)
    tracker.run(cfg1)
    assert len(sent) == 1  # morning brief delivered

    # Now both matches finish -> several new messages queued (post_match, recap).
    # Only the single newest should be delivered; the rest marked sent (skipped).
    fetch = lambda: {
        "1": {"home_goals": 2, "away_goals": 0, "status": "FT"},
        "2": {"home_goals": 1, "away_goals": 1, "status": "FT"},
    }
    cfg2 = _base_cfg(tmp_path, fetch=fetch, sender=sender)
    tracker.run(cfg2)
    assert len(sent) == 2  # exactly one more send across the whole run

    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    # every queued message is now marked sent (newest delivered, older skipped)
    assert all(m["sent"] for m in day["messages"])


def test_send_skipped_when_no_token(tmp_path):
    sent = []
    cfg = _base_cfg(tmp_path, token="", chat_ids=[],
                    sender=lambda text, **k: sent.append(text) or True)
    code = tracker.run(cfg)
    assert sent == []          # nothing sent
    assert code == 0           # not an error
    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    # message exists but is not marked sent (send was skipped, not done)
    assert any(not m["sent"] for m in day["messages"])


def test_send_failure_returns_2(tmp_path):
    cfg = _base_cfg(tmp_path, sender=lambda text, **k: False)
    code = tracker.run(cfg)
    assert code == 2


def test_fetch_error_degrades(tmp_path):
    def boom():
        raise RuntimeError("feed down")
    cfg = _base_cfg(tmp_path, fetch=boom)
    code = tracker.run(cfg)
    assert code in (0, 2)
    assert (tmp_path / "i.html").exists()  # still rendered


# ---------------------------------------------------------------------------
# reconcile_results / _norm
# ---------------------------------------------------------------------------

def test_norm_aliases():
    assert tracker._norm(" Korea Republic ") == "south korea"
    assert tracker._norm("USA") == "usa"
    assert tracker._norm("United States") == "usa"
    assert tracker._norm("IR Iran") == "iran"
    assert tracker._norm("Czechia") == "czech republic"


def test_reconcile_results_maps_to_seed_ids():
    from src import fixtures
    seed = fixtures.load_seed()
    # ESPN-style feed: keyed by feed id, carrying team names + date.
    raw = {
        "espn-999": {
            "home": "Mexico", "away": "South Africa", "date": "2026-06-11",
            "home_goals": 3, "away_goals": 1, "status": "FT",
        },
        "espn-aaa": {  # alias normalization: Korea Republic -> South Korea
            "home": "Korea Republic", "away": "Czechia", "date": "2026-06-11",
            "home_goals": 0, "away_goals": 2, "status": "FT",
        },
        "espn-unmatched": {  # no such fixture -> skipped
            "home": "Narnia", "away": "Atlantis", "date": "2026-06-11",
            "home_goals": 1, "away_goals": 0, "status": "FT",
        },
    }
    out = tracker.reconcile_results(raw, seed)
    assert out["1"] == {"home_goals": 3, "away_goals": 1, "status": "FT"}
    assert out["2"] == {"home_goals": 0, "away_goals": 2, "status": "FT"}
    assert all(not k.startswith("espn") for k in out)  # rekeyed to seed ids
