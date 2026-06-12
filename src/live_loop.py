"""
live_loop.py — matchday live-mode polling loop.

GitHub Actions throttles the */5 cron to multi-hour gaps, so a short-lived
state like ESPN's STATUS_HALFTIME (~15 min) is almost never sampled by
single-shot runs. In live mode one job rides through the whole match window:
poll every POLL_LIVE_S while any match may be live, wait at POLL_IDLE_S while
a kickoff is within LOOKAHEAD, and exit otherwise. Jobs are capped at 6h on
GitHub, so the loop stops at MAX_RUNTIME and signals the workflow to dispatch
a continuation run (kickoff spans reach 26h on the busiest days).
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

LIVE_SPAN = timedelta(hours=3)       # kickoff -> latest plausible final whistle
LOOKAHEAD = timedelta(hours=4)       # stay alive if a kickoff is this close
POLL_LIVE_S = 150                    # poll cadence while a match may be live
POLL_IDLE_S = 600                    # wait cadence while holding for kickoff
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
              *, clock: Callable[[], datetime] = None,
              sleep: Callable[[float], None] = None,
              max_runtime: timedelta = MAX_RUNTIME) -> tuple:
    """Run tracker cycles until the live window closes or runtime is capped.

    Returns (exit_code, continue_requested). `continue_requested` is True when
    the window is still active at the cap and the caller should dispatch a
    follow-up run. The exit code is the most recent cycle's code.
    """
    import time as _time
    if clock is None:
        clock = lambda: datetime.now(timezone.utc)
    if sleep is None:
        sleep = _time.sleep

    start = clock()
    code = run_once()

    while True:
        action = next_action(clock(), kickoffs)
        if action == "exit":
            return code, False
        if clock() - start >= max_runtime:
            return code, True
        sleep(POLL_LIVE_S if action == "poll" else POLL_IDLE_S)
        if action == "poll":
            code = run_once()


def _run_cmd(args: list) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def git_sync(run_cmd: Callable[[list], str] = _run_cmd) -> None:
    """Commit and push state.json + docs/ if they changed.

    Called after each live cycle so a hard-killed job never loses the
    sent-state that dedupes Telegram deliveries (and so the GitHub Pages
    archive stays current during long matchday loops).
    """
    dirty = run_cmd(["git", "status", "--porcelain", "state.json", "docs"])
    if not dirty.strip():
        return
    run_cmd(["git", "add", "state.json", "docs"])
    run_cmd(["git", "commit", "-m",
             "update: live tracker cycle"])
    run_cmd(["git", "pull", "--rebase"])
    run_cmd(["git", "push"])
