"""Tests for src/live_loop.py — matchday live-mode polling loop.

The loop exists because GitHub Actions throttles the */5 cron to multi-hour
gaps, so short-lived states (ESPN's ~15-minute STATUS_HALFTIME) are missed
unless a single job rides through the whole match window.
"""
from datetime import datetime, timedelta, timezone

from src import live_loop


UTC = timezone.utc


def _t(h, m=0):
    return datetime(2026, 6, 27, h, m, tzinfo=UTC)


# ---------------------------------------------------------------------------
# next_action — pure decision: poll / hold / exit
# ---------------------------------------------------------------------------

def test_poll_while_match_live():
    # Kickoff 21:00; at 21:50 the match is in its live span -> poll.
    assert live_loop.next_action(_t(21, 50), [_t(21)]) == "poll"


def test_poll_until_live_span_ends():
    # live span is LIVE_SPAN after kickoff; just inside -> poll, past -> not.
    ko = _t(21)
    inside = ko + live_loop.LIVE_SPAN - timedelta(minutes=1)
    past = ko + live_loop.LIVE_SPAN + timedelta(minutes=1)
    assert live_loop.next_action(inside, [ko]) == "poll"
    assert live_loop.next_action(past, [ko]) != "poll"


def test_hold_when_kickoff_within_lookahead():
    # 19:30 with a 21:00 kickoff (1.5h away, inside lookahead) -> hold.
    assert live_loop.next_action(_t(19, 30), [_t(21)]) == "hold"


def test_exit_when_next_kickoff_beyond_lookahead():
    # 10:00 with only a 21:00 kickoff (11h away) -> exit.
    assert live_loop.next_action(_t(10), [_t(21)]) == "exit"


def test_exit_when_all_kickoffs_long_past():
    assert live_loop.next_action(_t(12), [_t(0), _t(3)]) == "exit"


def test_exit_with_no_kickoffs():
    assert live_loop.next_action(_t(12), []) == "exit"


def test_poll_wins_over_hold_with_overlapping_matches():
    # One match live (21:00 KO at 21:30), another upcoming (23:30) -> poll.
    assert live_loop.next_action(_t(21, 30), [_t(21), _t(23, 30)]) == "poll"


# ---------------------------------------------------------------------------
# live_loop — loop runner with injected clock/sleep/runner
# ---------------------------------------------------------------------------

class FakeClock:
    """Clock that advances only via sleep()."""

    def __init__(self, start):
        self.now = start
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)


def test_runs_once_and_exits_when_no_window():
    clock = FakeClock(_t(10))
    calls = []
    code, cont = live_loop.live_loop(
        lambda: calls.append(1) or 0, [_t(21)],
        clock=clock, sleep=clock.sleep)
    assert calls == [1]
    assert clock.sleeps == []
    assert code == 0
    assert cont is False


def test_polls_through_live_window_then_exits():
    # Start mid-match at 21:10; only kickoff 21:00. Loop should poll every
    # POLL_LIVE_S until the live span ends, then exit without continuation.
    clock = FakeClock(_t(21, 10))
    calls = []
    code, cont = live_loop.live_loop(
        lambda: calls.append(1) or 0, [_t(21)],
        clock=clock, sleep=clock.sleep)
    # ~110 minutes of live span left at POLL_LIVE_S cadence.
    assert len(calls) > 10
    assert set(clock.sleeps) == {live_loop.POLL_LIVE_S}
    assert cont is False


def test_holds_with_idle_interval_before_kickoff():
    # 20:30, kickoff 21:00 -> at least one idle sleep before live polling.
    clock = FakeClock(_t(20, 30))
    live_loop.live_loop(lambda: 0, [_t(21)], clock=clock, sleep=clock.sleep)
    assert clock.sleeps[0] == live_loop.POLL_IDLE_S
    assert live_loop.POLL_LIVE_S in clock.sleeps


def test_requests_continuation_at_max_runtime():
    # Two kickoffs 3h apart keep the window active beyond a tiny max_runtime;
    # the loop must stop and signal that a follow-up run is needed.
    clock = FakeClock(_t(21, 10))
    code, cont = live_loop.live_loop(
        lambda: 0, [_t(21), _t(23, 30)],
        clock=clock, sleep=clock.sleep,
        max_runtime=timedelta(minutes=30))
    assert cont is True
    assert clock.now - _t(21, 10) <= timedelta(minutes=35)


def test_returns_last_nonzero_send_failure_code():
    # A send failure (2) on the last cycle must surface to CI.
    clock = FakeClock(_t(21, 10))
    codes = iter([0] * 5 + [2])

    def run_once():
        try:
            return next(codes)
        except StopIteration:
            return 2

    code, _ = live_loop.live_loop(
        run_once, [_t(21)], clock=clock, sleep=clock.sleep)
    assert code == 2


# ---------------------------------------------------------------------------
# git_sync — in-loop commit/push so a hard-killed job never loses sent-state
# ---------------------------------------------------------------------------

def test_git_sync_commits_and_pushes_when_dirty():
    seen = []

    def fake_run(args):
        seen.append(args)
        if args[:2] == ["git", "status"]:
            return " M state.json\n"
        return ""

    live_loop.git_sync(fake_run)
    joined = [" ".join(a) for a in seen]
    assert any(j.startswith("git add") for j in joined)
    assert any(j.startswith("git commit") for j in joined)
    # Detached-HEAD-proof, non-wedging persist: clear any stale rebase, then
    # reconcile with merge -X ours and push explicitly to main.
    assert "git rebase --abort" in joined
    assert any(j.startswith("git merge -X ours") for j in joined)
    assert "git push origin HEAD:main" in joined
    assert not any("pull --rebase" in j for j in joined)


def test_git_sync_noop_when_clean():
    seen = []

    def fake_run(args):
        seen.append(args)
        return ""

    live_loop.git_sync(fake_run)
    joined = [" ".join(a) for a in seen]
    assert not any(j.startswith("git commit") for j in joined)
    assert not any(j.startswith("git push") for j in joined)


# ---------------------------------------------------------------------------
# kickoffs_from_matches — fixture strings -> aware UTC datetimes
# ---------------------------------------------------------------------------

def test_kickoffs_from_matches_parses_z_suffix():
    matches = [
        {"id": "m1", "kickoff_utc": "2026-06-27T21:00:00Z"},
        {"id": "m2", "kickoff_utc": ""},
        {"id": "m3"},
    ]
    kos = live_loop.kickoffs_from_matches(matches)
    assert kos == [datetime(2026, 6, 27, 21, tzinfo=UTC)]
