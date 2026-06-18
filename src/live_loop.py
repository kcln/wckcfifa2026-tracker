"""
live_loop.py — matchday live-mode polling loop.

GitHub Actions throttles the */5 cron to multi-hour gaps, so a short-lived
state like ESPN's STATUS_HALFTIME (~15 min) is almost never sampled by
single-shot runs. In live mode one job rides through the whole match window,
running a FULL cycle every POLL_LIVE_S while a match may be live and every
POLL_IDLE_S otherwise.

Independently of that match cadence, the loop polls the Telegram inbox every
INBOX_TICK_S (~45s) so signups and approvals are processed within a minute at
any time of day — not stuck for up to 10 minutes (or, between matches, until
the throttled cron). The loop stays alive (self-chaining at MAX_RUNTIME, under
the 6h job cap) until the season ends, so the inbox is always being watched.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

LIVE_SPAN = timedelta(hours=3)       # kickoff -> latest plausible final whistle
LOOKAHEAD = timedelta(hours=4)       # stay alive if a kickoff is this close
POLL_LIVE_S = 150                    # full-cycle cadence while a match may be live
POLL_IDLE_S = 600                    # full-cycle cadence when nothing is live
INBOX_TICK_S = 45                    # Telegram inbox cadence, ALWAYS (signups/approvals)
MAX_RUNTIME = timedelta(hours=5, minutes=20)   # under the 6h job hard cap


def kickoffs_from_matches(matches: Iterable[dict]) -> list:
    """Aware UTC datetimes for every match carrying a kickoff_utc string."""
    out = []
    for m in matches:
        ko = m.get("kickoff_utc")
        if not ko:
            continue
        out.append(datetime.fromisoformat(ko.replace("Z", "+00:00")))
    return out


def next_action(now: datetime, kickoffs: Iterable[datetime]) -> str:
    """Decide what the loop should do at `now`: 'poll', 'hold', or 'exit'.

    'poll'  — some match is inside its live span (kickoff <= now < +LIVE_SPAN)
    'hold'  — no match live, but a kickoff is within LOOKAHEAD
    'exit'  — nothing live and nothing close
    """
    hold = False
    for ko in kickoffs:
        if ko <= now < ko + LIVE_SPAN:
            return "poll"
        if now < ko <= now + LOOKAHEAD:
            hold = True
    return "hold" if hold else "exit"


def live_loop(run_once: Callable[[], int], kickoffs: list,
              *, inbox_tick: Callable[[], None] = None,
              stop: Callable[[], bool] = None,
              clock: Callable[[], datetime] = None,
              sleep: Callable[[float], None] = None,
              max_runtime: timedelta = MAX_RUNTIME) -> tuple:
    """Watch the inbox every INBOX_TICK_S and run a full tracker cycle on the
    match cadence, until `stop()` (season over) or the runtime cap.

    Returns (exit_code, continue_requested). `continue_requested` is True when
    the cap is hit (the caller dispatches a follow-up run so the watcher stays
    alive); False when `stop()` ended it. `exit_code` is the most recent full
    cycle's code.

    `inbox_tick` is the lightweight Telegram-only poll run between full cycles;
    `run_once` is the full cycle (which also processes the inbox).
    """
    import time as _time
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleep = sleep or _time.sleep
    inbox_tick = inbox_tick or (lambda: None)
    stop = stop or (lambda: False)

    start = clock()
    code = run_once()
    last_full = clock()

    while True:
        if stop():                          # season ended -> wind down, no chain
            return code, False
        if clock() - start >= max_runtime:  # job cap -> chain a continuation
            return code, True
        action = next_action(clock(), kickoffs)
        interval = POLL_LIVE_S if action == "poll" else POLL_IDLE_S
        if clock() - last_full >= timedelta(seconds=interval):
            code = run_once()               # full cycle (fetch/render/send/inbox)
            last_full = clock()
        else:
            inbox_tick()                    # cheap Telegram poll between cycles
        sleep(INBOX_TICK_S)


def _run_cmd(args: list) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def git_sync(run_cmd: Callable[[list], str] = _run_cmd) -> None:
    """Commit and push state.json + docs/ if they changed.

    Called after each live cycle so a hard-killed job never loses the
    sent-state that dedupes Telegram deliveries (and so the GitHub Pages
    archive stays current during long matchday loops).

    Must be detached-HEAD-proof and must never wedge the repo. The CI runner
    can be in detached HEAD, and the old `git pull --rebase` would stop on the
    first conflict (docs/index.html is regenerated every cycle) leaving the repo
    mid-rebase in detached HEAD — after which every later commit/push failed and
    sent-state stopped persisting, re-sending messages on the next run. So:
    clear any leftover rebase, reconcile with `merge -X ours` (prefers our just
    -written state for the machine-owned files, never conflict-stops), and push
    explicitly to main so it works regardless of HEAD being detached.
    """
    dirty = run_cmd(["git", "status", "--porcelain",
                     "state.json", "subscribers.json", "docs"])
    if not dirty.strip():
        return
    run_cmd(["git", "rebase", "--abort"])   # no-op if no rebase in progress
    run_cmd(["git", "add", "state.json", "subscribers.json", "docs"])
    run_cmd(["git", "commit", "-m", "update: live tracker cycle"])
    run_cmd(["git", "fetch", "origin", "main"])
    run_cmd(["git", "merge", "-X", "ours", "--no-edit", "origin/main"])
    run_cmd(["git", "push", "origin", "HEAD:main"])
