#!/usr/bin/env python3
"""Send the onboarding menu (1-4 catch-up choice) to one approved subscriber.

Needed when a member is approved by editing subscribers.json directly instead
of tapping the bot's Approve button — that button callback is what normally
sends the menu, so a direct approval skips it. The member's 1-4 reply is
picked up by the next tracker inbox poll exactly like a button-approved one.

Usage:
    TELEGRAM_BOT_TOKEN=<token> python scripts/send_onboarding.py <chat_id>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import telegram_sender  # noqa: E402
from src.inbox import ONBOARD_MENU  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: send_onboarding.py <chat_id>")
    chat_id = sys.argv[1]
    subs = json.loads((ROOT / "subscribers.json").read_text())
    if chat_id not in subs.get("approved", []):
        raise SystemExit(f"chat {chat_id} is not approved — not sending")
    if chat_id in subs.get("onboarded", []):
        raise SystemExit(f"chat {chat_id} is already onboarded — not sending")
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("set TELEGRAM_BOT_TOKEN to send")
    ok = telegram_sender.send(ONBOARD_MENU, token, [chat_id])
    print(f"onboarding menu -> {chat_id}: {'sent' if ok else 'FAILED'}")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
