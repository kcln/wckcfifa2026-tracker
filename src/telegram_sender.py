"""Telegram Bot API delivery. Never raises; returns True only if all sends ok."""
from __future__ import annotations
import requests

def _default_poster(url, data):
    return requests.post(url, data=data, timeout=15)

def send(text: str, token: str, chat_ids: list[str], poster=_default_poster) -> bool:
    if not token or not chat_ids:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        for cid in chat_ids:
            r = poster(url, {"chat_id": cid, "text": text})
            if not getattr(r, "ok", False):
                return False
        return True
    except Exception:
        return False
