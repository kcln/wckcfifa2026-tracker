#!/usr/bin/env python3
"""Test-send a post-match result + the end-of-day recap to KC ONLY.

Builds one full-time result message (preferring a penalty shootout so the
'1 (3) - 1 (4)' format and bold winner are visible) and the daily recap for the
latest finished day from state.json, and sends both to KC's Telegram chat alone
— never the other subscribers. Used to preview message changes before they go
out to everyone on the next scheduled tracker run.

Usage:
    TELEGRAM_BOT_TOKEN=<token> ./venv/bin/python scripts/test_send_recap.py
    # add --dry-run to print the messages without sending
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


def _result_of(m: dict) -> dict:
    r = {"home_goals": m["hg"], "away_goals": m["ag"],
         "events": m.get("events", [])}
    if m.get("winner"):
        r["winner"] = m["winner"]
    if m.get("hpens") is not None and m.get("apens") is not None:
        r["home_pens"], r["away_pens"] = m["hpens"], m["apens"]
    return r


def _match_obj(m: dict, date: str) -> dict:
    p = m.get("pred") or {}
    return {"home": m["home"], "away": m["away"], "date": date,
            "venue": m.get("venue", ""), "kickoff_utc": m.get("kickoff_utc", ""),
            "prediction": {"home": p.get("home", 0), "draw": p.get("draw", 0),
                           "away": p.get("away", 0)},
            "result": _result_of(m)}


def _finished(state: dict) -> list[tuple]:
    board = sorted(state.get("board") or [], key=lambda d: d["date"])
    return [(d["date"], m) for d in board for m in d.get("matches", [])
            if m.get("status") == "FT" and m.get("hg") is not None]


def build_post_match(state: dict) -> str:
    fts = _finished(state)
    if not fts:
        raise SystemExit("no finished match in state.json")
    pens = [x for x in fts if x[1].get("hpens") is not None]
    date, m = pens[-1] if pens else fts[-1]      # prefer a shootout to showcase
    overall = (sum(1 for _, mm in fts if mm.get("hit")), len(fts))
    return message_builder.post_match(_match_obj(m, date), overall=overall)


def build_recap(state: dict) -> tuple[str, str]:
    board = sorted(state.get("board") or [], key=lambda d: d["date"])
    day = next((d for d in reversed(board)
                if any(x.get("status") == "FT" for x in d.get("matches", []))), None)
    if not day:
        raise SystemExit("no finished day in state.json")
    matches = [_match_obj(m, day["date"]) for m in day["matches"]
               if m.get("status") == "FT" and m.get("hg") is not None]
    day_hits = sum(1 for m in day["matches"] if m.get("status") == "FT" and m.get("hit"))
    day_total = sum(1 for m in day["matches"] if m.get("status") == "FT")
    all_ft = _finished(state)
    overall = (sum(1 for _, m in all_ft if m.get("hit")), len(all_ft))
    tables = state.get("groups") or {}
    qualified = knockout.clinched_all(tables, state.get("schedule") or [])
    recap = message_builder.daily_recap(
        day["date"], matches, tables, day_acc=(day_hits, day_total),
        overall_acc=overall, qualified=qualified)
    return day["date"], recap


def _strip(msg: str) -> str:
    return msg.replace("<code>", "").replace("</code>", "")


def main() -> None:
    state = json.loads((ROOT / "state.json").read_text())
    pm = build_post_match(state)
    date_iso, recap = build_recap(state)
    print("--- post-match (preview) ---\n" + _strip(pm))
    print(f"\n--- recap for {date_iso} (preview) ---\n" + _strip(recap))
    print("\n--- end preview ---")

    if "--dry-run" in sys.argv:
        print("dry-run: not sent.")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("set TELEGRAM_BOT_TOKEN to send (or pass --dry-run)")
    s1 = telegram_sender.send(pm, token, [KC_CHAT_ID])
    s2 = telegram_sender.send(recap, token, [KC_CHAT_ID])
    print(f"sent to KC ({KC_CHAT_ID}): post_match={s1} recap={s2}")


if __name__ == "__main__":
    main()
