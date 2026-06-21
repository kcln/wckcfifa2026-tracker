#!/usr/bin/env python3
"""Test-send the end-of-day recap to KC ONLY (never the other subscribers).

Builds the daily recap for the latest day with finished results from state.json
— including the new "Q = Qualified for Round of 32" markers in the group tables
— and sends it to KC's Telegram chat alone. Used to preview message changes
before they go out to everyone on the next scheduled tracker run.

Usage:
    TELEGRAM_BOT_TOKEN=<token> ./venv/bin/python scripts/test_send_recap.py
    # add --dry-run to print the message without sending
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import knockout, message_builder, telegram_sender  # noqa: E402

KC_CHAT_ID = "391401564"          # KC only — this script never broadcasts.
ROOT = Path(__file__).resolve().parent.parent


def _matches_for_recap(day: dict) -> list[dict]:
    """Reshape a board day's finished matches into daily_recap's input shape."""
    out = []
    for m in day.get("matches", []):
        if m.get("status") != "FT" or m.get("hg") is None:
            continue
        p = m.get("pred") or {}
        out.append({
            "home": m["home"], "away": m["away"],
            "kickoff_utc": m.get("kickoff_utc", ""), "date": day["date"],
            "venue": m.get("venue", ""),
            "prediction": {"home": p.get("home", 0), "draw": p.get("draw", 0),
                           "away": p.get("away", 0)},
            "result": {"home_goals": m["hg"], "away_goals": m["ag"],
                       "events": m.get("events", [])},
        })
    return out


def build_recap(state: dict) -> tuple[str, str]:
    board = sorted(state.get("board") or [], key=lambda d: d["date"])
    day = next((d for d in reversed(board)
                if any(x.get("status") == "FT" for x in d.get("matches", []))), None)
    if not day:
        raise SystemExit("no finished day in state.json")

    matches = _matches_for_recap(day)
    day_hits = sum(1 for m in day["matches"] if m.get("status") == "FT" and m.get("hit"))
    day_total = sum(1 for m in day["matches"] if m.get("status") == "FT")
    all_ft = [m for d in board for m in d["matches"] if m.get("status") == "FT"]
    overall = (sum(1 for m in all_ft if m.get("hit")), len(all_ft))

    tables = state["groups"]
    qualified = knockout.clinched_set(tables, state.get("schedule") or [])
    recap = message_builder.daily_recap(
        day["date"], matches, tables, day_acc=(day_hits, day_total),
        overall_acc=overall, qualified=qualified)
    return day["date"], recap


def main() -> None:
    state = json.loads((ROOT / "state.json").read_text())
    date_iso, recap = build_recap(state)
    print(f"--- recap for {date_iso} (preview) ---\n")
    print(recap.replace("<code>", "").replace("</code>", ""))
    print("\n--- end preview ---")

    if "--dry-run" in sys.argv:
        print("dry-run: not sent.")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("set TELEGRAM_BOT_TOKEN to send (or pass --dry-run)")
    sent = telegram_sender.send(recap, token, [KC_CHAT_ID])
    print(f"sent to KC ({KC_CHAT_ID}): {sent}")


if __name__ == "__main__":
    main()
