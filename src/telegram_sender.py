"""Telegram Bot API delivery. Never raises; returns True only if all sends ok.

Every message is sent as HTML and gets a clickable footer link to the live
archive. Bodies are HTML-escaped first so team/scorer names containing & < >
(e.g. "Bosnia & Herzegovina") can never break the markup.
"""
from __future__ import annotations
from html import escape

import requests

ARCHIVE_URL = "https://kcln.github.io/wckcfifa2026-tracker/"
_FOOTER = f'\n\n<a href="{ARCHIVE_URL}">\U0001F517 Open the live tracker</a>'


def _default_poster(url, data):
    return requests.post(url, data=data, timeout=15)


def _format(text: str) -> str:
    """HTML-escape the plain body and append the hyperlink footer. `<code>`
    blocks (the monospace standings table) are preserved — their inner text is
    still escaped, only the tags survive — so Telegram renders fixed-width
    columns that line up, WITHOUT the "</>" badge a <pre> block would add."""
    out = escape(text, quote=False)
    out = out.replace("&lt;code&gt;", "<code>").replace("&lt;/code&gt;", "</code>")
    return out + _FOOTER


def send(text: str, token: str, chat_ids: list[str], poster=_default_poster) -> bool:
    if not token or not chat_ids:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = _format(text)
    try:
        for cid in chat_ids:
            r = poster(url, {"chat_id": cid, "text": body,
                             "parse_mode": "HTML",
                             "disable_web_page_preview": "true"})
            if not getattr(r, "ok", False):
                return False
        return True
    except Exception:
        return False
