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

    ht = [s for s in sent if "Half-time:" in s]
    assert len(ht) == 1
    assert "1 - 0" in ht[0]

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
    # Word-order variant: squashing keeps order, so this needs an explicit alias.
    assert tracker._norm("Congo DR") == tracker._norm("DR Congo")


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
                                  "status": "FT", "clock": "", "events": []}


def test_reconcile_congo_word_order_feed_maps_to_seed_live():
    # Jun-17 live bug: ESPN's "Congo DR" vs seed "DR Congo" failed to reconcile,
    # so the live hero never populated (and the FT result would have dropped too).
    from src import fixtures
    seed = fixtures.load_seed()
    drc = next(m for m in seed["matches"]
               if "Congo" in (m["home"] + m["away"]))
    feed_home = "Congo DR" if drc["home"] == "DR Congo" else drc["home"]
    feed_away = "Congo DR" if drc["away"] == "DR Congo" else drc["away"]
    raw = {"espn-drc": {
        "home": feed_home, "away": feed_away, "date": drc["date"],
        "home_goals": 1, "away_goals": 1, "status": "LIVE", "clock": "64'"}}
    out = tracker.reconcile_results(raw, seed)
    assert out.get(drc["id"], {}).get("status") == "LIVE"
    assert tracker.build_live(seed, out)[0]["id"] == drc["id"]


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
                        "clock": "", "events": []}
    assert out["2"] == {"home_goals": 0, "away_goals": 2, "status": "FT",
                        "clock": "", "events": []}
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


def test_norm_unifies_turkiye_endonym():
    # June-13 live bug: ESPN 'Türkiye' vs seed 'Turkey' dropped the result
    # and blocked the whole daily recap.
    assert tracker._norm("Türkiye") == tracker._norm("Turkey")
    assert tracker._norm("Turkiye") == tracker._norm("Turkey")


def test_day_clock_complete():
    from datetime import datetime, timezone, timedelta
    ms = [{"kickoff_utc": "2026-06-13T19:00:00Z"},
          {"kickoff_utc": "2026-06-14T04:00:00Z"}]  # last KO 04:00 UTC
    before = datetime(2026, 6, 14, 6, 0, tzinfo=timezone.utc)   # +2h, not done
    after = datetime(2026, 6, 14, 8, 0, tzinfo=timezone.utc)    # +4h, done
    assert tracker._day_clock_complete(ms, before) is False
    assert tracker._day_clock_complete(ms, after) is True
    # a match with no kickoff -> cannot assert completeness
    assert tracker._day_clock_complete(ms + [{}], after) is False


def test_build_catchup_options():
    stateobj = {"days": [{"date": "2026-06-14", "messages": [
        {"type": "morning_brief", "body": "BRIEF"},
        {"type": "half_time", "body": "HT"},
        {"type": "post_match", "body": "FT"},
        {"type": "daily_recap", "body": "RECAP"}]}]}
    iso = "2026-06-14"
    assert tracker.build_catchup(stateobj, iso, 1) == ["BRIEF", "HT", "FT", "RECAP"]
    assert tracker.build_catchup(stateobj, iso, 2) == ["BRIEF"]
    assert tracker.build_catchup(stateobj, iso, 3) == ["HT", "FT"]
    assert tracker.build_catchup(stateobj, iso, 4) == ["RECAP"]


def test_build_catchup_empty_day_has_friendly_fallback():
    out = tracker.build_catchup({"days": []}, "2026-06-14", 1)
    assert len(out) == 1 and "live" in out[0].lower()


def test_prev_day_iso():
    assert tracker._prev_day_iso("2026-06-14") == "2026-06-13"
    assert tracker._prev_day_iso("2026-07-01") == "2026-06-30"


def test_recap_and_result_fire_for_prior_day_after_midnight():
    # A match KICKS OFF on 06-13 (PT) but finishes after midnight; the tracker
    # is now on 06-14. Its result AND the 06-13 recap must still fire.
    merged = {"groups": {"A": ["X", "Y"]},
              "matches": [
                  {"id": "1", "home": "X", "away": "Y", "date": "2026-06-13",
                   "stage": "group", "group": "A",
                   "kickoff_utc": "2026-06-14T04:00:00Z",
                   "result": {"home_goals": 2, "away_goals": 0}}]}
    st = {"days": [], "season_ended": False}
    mp = lambda h, a: {"home": 0.5, "draw": 0.3, "away": 0.2}
    tracker._due_messages(st, merged, mp, "2026-06-14")
    day = next(d for d in st["days"] if d["date"] == "2026-06-13")
    types = [m["type"] for m in day["messages"]]
    assert "post_match" in types and "daily_recap" in types


def test_tournament_over():
    merged = {"matches": [{"id": "f", "stage": "final", "date": "2026-07-19"}]}
    assert tracker._tournament_over(merged, {"season_ended": True}, "2026-06-14")
    assert not tracker._tournament_over(merged, {}, "2026-07-19")
    assert not tracker._tournament_over(merged, {}, "2026-07-21")  # within 3d grace
    assert tracker._tournament_over(merged, {}, "2026-07-23")      # past final+3d


def test_accuracy_counts_hits_over_resolved():
    merged = {"matches": [
        {"id": "1", "home": "A", "away": "B", "date": "2026-06-14",
         "kickoff_utc": "2026-06-14T10:00:00Z",
         "result": {"home_goals": 2, "away_goals": 0}},   # home win
        {"id": "2", "home": "C", "away": "D", "date": "2026-06-14",
         "kickoff_utc": "2026-06-14T13:00:00Z",
         "result": {"home_goals": 0, "away_goals": 1}},   # away win
        {"id": "3", "home": "E", "away": "F", "date": "2026-06-15",
         "kickoff_utc": "2026-06-15T10:00:00Z"}]}          # unresolved
    # match_prob always predicts home win
    mp = lambda h, a: {"home": 0.8, "draw": 0.1, "away": 0.1}
    assert tracker._accuracy(merged, mp) == (1, 2)               # only match 1 hit
    assert tracker._accuracy(merged, mp, date_iso="2026-06-14") == (1, 2)
    # cumulative through the first kickoff only counts match 1
    assert tracker._accuracy(merged, mp,
                             until_kickoff="2026-06-14T10:00:00Z") == (1, 1)


def test_results_persist_across_feed_window(tmp_path):
    # Match 1 finishes; next cycle the feed no longer reports it (rolling
    # window). Its result must persist so accuracy stays correct.
    cfg1 = _base_cfg(tmp_path, token="", chat_ids=[],
                     fetch=lambda: {"1": {"home_goals": 2, "away_goals": 0,
                                          "status": "FT"}})
    tracker.run(cfg1)
    s = json.loads((tmp_path / "state.json").read_text())
    assert s["results"]["1"]["home_goals"] == 2

    # Feed drops match 1 entirely on the next cycle.
    cfg2 = _base_cfg(tmp_path, token="", chat_ids=[], fetch=lambda: {})
    tracker.run(cfg2)
    s = json.loads((tmp_path / "state.json").read_text())
    assert s["results"]["1"]["home_goals"] == 2   # still remembered


def test_result_not_resent_when_minute_revised(tmp_path):
    # ESPN first reports a goal at 88', then revises it to 89'. The full-time
    # message body changes but the result must be sent only ONCE.
    feed88 = lambda: {"1": {"home_goals": 2, "away_goals": 2, "status": "FT",
                            "events": [{"kind": "goal", "player": "Kamada",
                                        "team": "Japan", "minute": "88'"}]}}
    feed89 = lambda: {"1": {"home_goals": 2, "away_goals": 2, "status": "FT",
                            "events": [{"kind": "goal", "player": "Kamada",
                                        "team": "Japan", "minute": "89'"}]}}
    sent = []
    s = lambda text, **k: sent.append(text) or True
    tracker.run(_base_cfg(tmp_path, fetch=feed88, sender=s))
    tracker.run(_base_cfg(tmp_path, fetch=feed89, sender=s))
    saved = json.loads((tmp_path / "state.json").read_text())
    day = next(d for d in saved["days"] if d["date"] == "2026-06-11")
    pms = [m for m in day["messages"] if m["type"] == "post_match"]
    assert len(pms) == 1   # one result per match, minute revision ignored


def test_build_live_and_board_overlay_in_progress():
    from src import fixtures
    seed = fixtures.load_seed()
    m = seed["matches"][0]               # any real fixture
    feed = {m["id"]: {"home_goals": 1, "away_goals": 0, "status": "LIVE",
                      "clock": "50'", "events": []}}
    live = tracker.build_live(seed, feed)
    assert live and live[-1]["home"] == m["home"] and live[-1]["clock"] == "50'"

    merged = fixtures.merge_results(seed, {})   # nothing finished
    mp = lambda h, a: {"home": 0.5, "draw": 0.3, "away": 0.2}
    board = tracker.build_board(merged, mp, {m["date"]}, live=feed)
    entry = next(x for d in board for x in d["matches"] if x["id"] == m["id"])
    assert entry["status"] == "live" and entry["hg"] == 1 and entry["clock"] == "50'"


def test_send_pending_prunes_blocked_chat_and_still_marks_sent(tmp_path):
    # One subscriber blocked the bot: the message must still mark sent (no
    # perpetual re-send) and the dead chat must be pruned from subscribers.json.
    from src import subscribers
    subs_path = tmp_path / "subscribers.json"
    subscribers.save(subs_path, {"approved": ["A", "B", "C"], "pending": {},
                                 "onboarded": ["A", "B", "C"],
                                 "last_update_id": 0})
    stateobj = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "morning_brief", "body": "Brief", "sent": False,
         "hash": "h", "key": "mb-2026-06-11"}]}], "results": {}}

    def sender(text, token=None, chat_ids=None, on_dead=None):
        if on_dead:
            on_dead("B")          # B is permanently dead
        return True               # A and C delivered → safe to mark sent

    cfg = _base_cfg(tmp_path, chat_ids=["A", "B", "C"], sender=sender)
    code = tracker._send_pending(stateobj, cfg)
    assert code == 0
    assert stateobj["days"][0]["messages"][0]["sent"] is True
    subs = subscribers.load(subs_path)
    assert subs["approved"] == ["A", "C"]      # B pruned
    assert subs["onboarded"] == ["A", "C"]


def test_build_board_resolves_knockout_slot_tokens():
    from src import fixtures, knockout
    seed = fixtures.load_seed()
    merged = fixtures.merge_results(seed, {})
    mp = lambda h, a: {"home": 0.4, "draw": 0.3, "away": 0.3}
    # Pretend every group is decided so 1X/2X slots resolve.
    tables = {}
    for g, teams in merged["groups"].items():
        tables[g] = [{"team": t, "played": 3, "points": 9 - i, "gd": 5 - i,
                      "gf": 6, "ga": 1} for i, t in enumerate(teams)]
    resolved = knockout.resolve_bracket(merged["matches"], tables, {})
    m73 = next(m for m in merged["matches"] if str(m["id"]) == "73")
    board = tracker.build_board(merged, mp, {m73["date"]}, resolved=resolved)
    entry = next(x for d in board for x in d["matches"] if str(x["id"]) == "73")
    # 2A/2B are now real team names, not the raw tokens
    assert not knockout.is_descriptor(entry["home"])
    assert not knockout.is_descriptor(entry["away"])
    assert entry["home"] == tables["A"][1]["team"]   # 2A = group A runner-up


def test_reconcile_results_carries_penalty_winner():
    feed = {"e": {"home": "Germany", "away": "Paraguay", "date": "2026-06-29",
                  "home_goals": 1, "away_goals": 1, "status": "FT",
                  "winner": "Paraguay", "home_pens": 3, "away_pens": 4, "events": []}}
    seed = {"matches": [{"id": "74", "home": "Germany", "away": "Paraguay",
                         "date": "2026-06-29"}]}
    out = tracker.reconcile_results(feed, seed)
    assert out["74"]["winner"] == "Paraguay"
    assert out["74"]["home_pens"] == 3 and out["74"]["away_pens"] == 4


def test_accuracy_counts_shootout_winner_pick_as_hit():
    merged = {"matches": [{"id": "75", "home": "1F", "away": "2C",
                           "date": "2026-06-29", "kickoff_utc": "2026-06-29T19:00:00Z",
                           "result": {"home_goals": 1, "away_goals": 1,
                                      "winner": "Morocco"}}]}
    def mp(h, a):
        return ({"home": 0.3, "draw": 0.3, "away": 0.4} if a == "Morocco"
                else {"home": 0.4, "draw": 0.3, "away": 0.3})
    hits, total = tracker._accuracy(merged, mp, resolved={"75": ("Netherlands", "Morocco")})
    assert (hits, total) == (1, 1)


def test_build_board_folds_draw_for_knockouts():
    merged = {"matches": [
        {"id": "83", "home": "Portugal", "away": "Croatia", "date": "2026-07-02",
         "kickoff_utc": "2026-07-02T20:00:00Z", "venue": "Toronto", "stage": "R32"},
        {"id": "5", "home": "Mexico", "away": "South Korea", "date": "2026-07-02",
         "kickoff_utc": "2026-07-02T23:00:00Z", "venue": "Mexico City", "stage": "group"}]}
    mp = lambda h, a: {"home": 0.361, "draw": 0.276, "away": 0.363}
    board = tracker.build_board(merged, mp, {"2026-07-02"})
    ko = next(x for d in board for x in d["matches"] if x["id"] == "83")
    grp = next(x for d in board for x in d["matches"] if x["id"] == "5")
    # knockout: draw folded 50/50 into the sides, pick is a team
    assert ko["pred"]["draw"] == 0.0
    assert abs(ko["pred"]["home"] - 0.499) < 0.001
    assert abs(ko["pred"]["away"] - 0.501) < 0.001
    assert ko["pred"]["pick"] == "Croatia"
    # group stage keeps the raw three-way
    assert grp["pred"]["draw"] == 0.276
