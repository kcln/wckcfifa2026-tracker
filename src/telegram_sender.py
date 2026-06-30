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
    # Keep the markup tags we emit on purpose (monospace tables + bold winners);
    # everything else — including team names with & < > — stays escaped.
    for tag in ("<code>", "</code>", "<b>", "</b>"):
        out = out.replace(escape(tag, quote=False), tag)
    return out + _FOOTER


def send(text: str, token: str, chat_ids: list[str], poster=_default_poster,
         on_dead=None) -> bool:
    """Broadcast `text` to every chat id. ALWAYS attempts all recipients — a
    failure for one must never skip the rest (that silently dropped later
    subscribers and, because the message then never marked sent, re-spammed the
    earlier ones every cycle).

    Failures are classified:
      * permanent (HTTP 400/403 — user blocked the bot, deactivated, or chat
        not found): that chat can never receive, so it does NOT hold up the
        broadcast; `on_dead(chat_id)` is invoked so the caller can prune it.
      * transient (network error, 429 rate-limit, 5xx): worth retrying.

    Returns True when the message is delivered as well as it ever will be (every
    chat either succeeded or is permanently dead) — i.e. safe to mark sent.
    Returns False only when a transient failure remains, so the caller retries
    next cycle (without skipping anyone).
    """
    if not token or not chat_ids:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = _format(text)
    transient = False
    for cid in chat_ids:
        try:
            r = poster(url, {"chat_id": cid, "text": body,
                             "parse_mode": "HTML",
                             "disable_web_page_preview": "true"})
        except Exception:
            transient = True          # network blip → retry, don't skip others
            continue
        if getattr(r, "ok", False):
            continue                  # delivered
        if getattr(r, "status_code", None) in (400, 403):
            if on_dead is not None:   # blocked/deactivated/not-found → permanent
                on_dead(cid)
        else:
            transient = True          # 429 / 5xx / unknown → retry later
    return not transient
