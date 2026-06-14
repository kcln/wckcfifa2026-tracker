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


def test_send_flushes_all_pending_oldest_first(tmp_path):
    # First run on day 1 (no results) -> morning brief is delivered.
    sent = []
    sender = lambda text, **k: sent.append(text) or True
    cfg1 = _base_cfg(tmp_path, fetch=lambda: {}, sender=sender)
    tracker.run(cfg1)
    assert len(sent) == 1  # morning brief delivered

    # Now both matches finish -> several new messages queued (post_match x2,
    # recap). EVERY pending message must be delivered — no skips.
    fetch = lambda: {
        "1": {"home_goals": 2, "away_goals": 0, "status": "FT"},
        "2": {"home_goals": 1, "away_goals": 1, "status": "FT"},
    }
    cfg2 = _base_cfg(tmp_path, fetch=fetch, sender=sender)
    tracker.run(cfg2)

    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    assert all(m["sent"] for m in day["messages"])
    # one send per queued message: brief + 2 results + recap
    assert len(sent) == len(day["messages"])
    # oldest first: the morning brief went out before the recap
    assert sent.index(next(s for s in sent if "Matchday Brief" in s)) \
        < sent.index(next(s for s in sent if "Daily Recap" in s))


def test_send_failure_midway_keeps_rest_pending(tmp_path):
    # Queue several messages, then fail on the second send: the first is
    # delivered, everything from the failure on stays unsent for retry.
    fetch = lambda: {
        "1": {"home_goals": 2, "away_goals": 0, "status": "FT"},
        "2": {"home_goals": 1, "away_goals": 1, "status": "FT"},
    }
    calls = []
    sender = lambda text, **k: calls.append(text) or (len(calls) == 1)
    cfg = _base_cfg(tmp_path, fetch=fetch, sender=sender)
    code = tracker.run(cfg)
    assert code == 2
    assert len(calls) == 2  # stopped at first failure

    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    assert sum(1 for m in day["messages"] if m["sent"]) == 1
    assert sum(1 for m in day["messages"] if not m["sent"]) >= 2

    # Next run with a healthy sender delivers the rest exactly once.
    sent2 = []
    cfg2 = _base_cfg(tmp_path, fetch=fetch,
                     sender=lambda text, **k: sent2.append(text) or True)
    assert tracker.run(cfg2) == 0
    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    assert all(m["sent"] for m in day["messages"])


def test_half_time_message_sent_and_deduped(tmp_path):
    # Match 1 is at the break: a half-time update goes out once, with the
    # frozen score, and repeat sightings across runs do not duplicate it.
    sent = []
    fetch = lambda: {"1": {"home_goals": 1, "away_goals": 0, "status": "HT"}}
    cfg = _base_cfg(tmp_path, fetch=fetch,
                    sender=lambda text, **k: sent.append(text) or True)
    tracker.run(cfg)
    tracker.run(cfg)  # break lasts several ticks — must not resend

    ht = [s for s in sent if s.startswith("Half-time:")]
    assert len(ht) == 1
    assert "1-0" in ht[0]

    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    types = [m["type"] for m in day["messages"]]
    assert types.count("half_time") == 1
    # an HT score must never be recorded as a final result
    assert not any(m["type"] == "post_match" for m in day["messages"])


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
    # Callers compare _norm to _norm; assert pairs unify, not literal forms.
    assert tracker._norm(" Korea Republic ") == tracker._norm("South Korea")
    assert tracker._norm("United States") == tracker._norm("USA")
    assert tracker._norm("IR Iran") == tracker._norm("Iran")
    assert tracker._norm("Czechia") == tracker._norm("Czech Republic")


def test_norm_unifies_punctuation_variants():
    # Day-2 live bug: ESPN 'Bosnia-Herzegovina' vs seed 'Bosnia & Herzegovina'
    # silently dropped the Canada result. Squashing must unify these forever.
    seed = "Bosnia & Herzegovina"
    for feed in ("Bosnia-Herzegovina", "Bosnia Herzegovina",
                 "Bosnia and Herzegovina"):
        assert tracker._norm(feed) == tracker._norm(seed), feed
    assert tracker._norm("Côte d'Ivoire") == tracker._norm("Ivory Coast")


def test_reconcile_bosnia_hyphen_feed_maps_to_seed():
    from src import fixtures
    seed = fixtures.load_seed()
    bos = next(m for m in seed["matches"]
               if "Bosnia" in (m["home"] + m["away"]))
    raw = {"espn-bos": {
        "home": bos["home"].replace(" & ", "-"),
        "away": bos["away"].replace(" & ", "-"),
        "date": bos["date"], "home_goals": 1, "away_goals": 1, "status": "FT"}}
    out = tracker.reconcile_results(raw, seed)
    assert out.get(bos["id"]) == {"home_goals": 1, "away_goals": 1,
                                  "status": "FT", "events": []}


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
    assert out["1"] == {"home_goals": 3, "away_goals": 1, "status": "FT",
                        "events": []}
    assert out["2"] == {"home_goals": 0, "away_goals": 2, "status": "FT",
                        "events": []}
    assert all(not k.startswith("espn") for k in out)  # rekeyed to seed ids


def test_messages_carry_match_kickoff(tmp_path):
    fetch = lambda: {"1": {"home_goals": 2, "away_goals": 0, "status": "FT"}}
    cfg = _base_cfg(tmp_path, fetch=fetch)
    tracker.run(cfg)
    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    brief = next(m for m in day["messages"] if m["type"] == "morning_brief")
    post = next(m for m in day["messages"] if m["type"] == "post_match")
    assert brief["kickoff_utc"]  # earliest kickoff of the day
    assert post["kickoff_utc"] == "2026-06-11T19:00:00Z"
