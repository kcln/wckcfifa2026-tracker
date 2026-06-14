"""Committed-file subscriber store (subscribers.json).

Holds the broadcast list and signup state so approvals persist across runs
without touching the write-only TELEGRAM_CHAT_IDS secret (which the Actions
job cannot write). Chat IDs are numeric and live in the public repo; member
names are NEVER persisted here — only used transiently in the approval prompt.

Schema:
  approved       list[str]  chat IDs that receive broadcasts
  pending        dict       {chat_id: {"ts": iso}}  awaiting KC's approval
  onboarded      list[str]  chat IDs that finished the 1-4 catch-up menu
  last_update_id int        getUpdates offset high-water mark
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT = {"approved": [], "pending": {}, "onboarded": [], "last_update_id": 0}


def load(path) -> dict:
    """Load subscribers.json. On first run (no file) seed the approved list
    from the legacy TELEGRAM_CHAT_IDS secret so we never lose existing
    subscribers; those are treated as already-onboarded."""
    p = Path(path)
    if p.exists():
        d = json.loads(p.read_text())
        for k, v in DEFAULT.items():
            d.setdefault(k, json.loads(json.dumps(v)))
        return d
    seed = [c for c in os.environ.get("TELEGRAM_CHAT_IDS", "").split(",") if c]
    d = json.loads(json.dumps(DEFAULT))
    d["approved"] = list(seed)
    d["onboarded"] = list(seed)
    return d


def save(path, subs: dict) -> None:
    Path(path).write_text(json.dumps(subs, indent=2) + "\n", encoding="utf-8")
