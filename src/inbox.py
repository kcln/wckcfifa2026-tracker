"""Inbound Telegram handling: the signup approval + onboarding pipeline.

GitHub Actions has no webhook, so the bot polls getUpdates each tracker cycle.
Flow:
  1. A new chat sends /start  -> added to `pending`; the approver (KC) is DM'd
     an Approve / Decline inline-button prompt.
  2. Approver taps Approve     -> chat moves pending -> approved; the new member
     gets the numbered onboarding menu (1-4).
  3. New member replies 1-4    -> gets that one-time catch-up, then is marked
     onboarded and receives all future broadcasts like everyone else.
  4. Anyone sends /stop        -> removed from approved.

`process_updates` is pure w.r.t. I/O: it takes the fetched updates plus small
callables (`send`, `answer_cb`, `catchup`) so it is fully unit-testable. The
real wiring lives in `poll` + the `_requests_*` helpers.
"""
from __future__ import annotations

ONBOARD_MENU = (
    "\U0001F44B You're approved — welcome to the FIFA World Cup 2026 tracker!\n\n"
    "One quick thing: what would you like right now? Reply with a number:\n\n"
    "1️⃣ Today's match brief + day summary + updates so far\n"
    "2️⃣ Only today's match brief\n"
    "3️⃣ Only updates (half-time + results)\n"
    "4️⃣ Only the day's summary\n\n"
    "After this one-time choice you'll get all match-day updates automatically. "
    "Reply /stop anytime to leave."
)


def _approval_prompt(name: str, chat_id: str) -> tuple[str, dict]:
    text = (
        "\U0001F195 New sign-up request\n"
        f"{name or 'Someone'} pressed Start on the bot.\n"
        f"Chat ID: {chat_id}\n\n"
        "Approve to add them and send their welcome + catch-up."
    )
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"approve:{chat_id}"},
        {"text": "❌ Decline", "callback_data": f"deny:{chat_id}"},
    ]]}
    return text, keyboard


def process_updates(updates, subs, *, approver, send, answer_cb, catchup,
                    now_ts=""):
    """Mutate `subs` for each update and emit Telegram messages via callbacks.

    Params (callables so this stays I/O-free and testable):
      send(chat_id, text, reply_markup=None) -> None
      answer_cb(callback_query_id, text="") -> None
      catchup(option:int) -> list[str]   bodies for onboarding choice 1-4
    Returns the new last_update_id high-water mark.
    """
    approver = str(approver)
    approved = subs.setdefault("approved", [])
    pending = subs.setdefault("pending", {})
    onboarded = subs.setdefault("onboarded", [])
    last = subs.get("last_update_id", 0)

    for u in updates:
        uid = u.get("update_id", 0)
        if uid > last:
            last = uid

        # ---- KC's Approve / Decline button taps ----
        cb = u.get("callback_query")
        if cb:
            data = cb.get("data") or ""
            frm = str((cb.get("from") or {}).get("id"))
            cq_id = cb.get("id")
            if frm == approver and ":" in data:
                action, target = data.split(":", 1)
                if action == "approve":
                    pending.pop(target, None)
                    if target not in approved:
                        approved.append(target)
                    answer_cb(cq_id, "Approved ✅")
                    send(target, ONBOARD_MENU)
                elif action == "deny":
                    pending.pop(target, None)
                    answer_cb(cq_id, "Declined")
            else:
                answer_cb(cq_id, "")
            continue

        # ---- plain text messages ----
        msg = u.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        text = (msg.get("text") or "").strip()
        if not chat_id or not text:
            continue

        if text.startswith("/start"):
            if chat_id in approved or chat_id in pending:
                continue
            pending[chat_id] = {"ts": now_ts}
            name = " ".join(x for x in (chat.get("first_name"),
                                        chat.get("last_name")) if x)
            ptext, kb = _approval_prompt(name, chat_id)
            send(approver, ptext, kb)
            continue

        if text.startswith("/stop"):
            if chat_id in approved:
                approved.remove(chat_id)
            if chat_id in onboarded:
                onboarded.remove(chat_id)
            send(chat_id, "You're unsubscribed. Reply /start to rejoin.")
            continue

        # onboarding choice 1-4 from an approved-but-not-onboarded member
        if (text in ("1", "2", "3", "4")
                and chat_id in approved and chat_id not in onboarded):
            for body in catchup(int(text)):
                send(chat_id, body)
            onboarded.append(chat_id)
            continue

    subs["last_update_id"] = last
    return last


# ---------------------------------------------------------------------------
# Real Telegram I/O (thin wrappers; the logic above stays testable)
# ---------------------------------------------------------------------------

def poll(token: str, offset: int, *, get=None):
    """Fetch pending updates from getUpdates starting at `offset`. Returns []
    on any error so a transient failure never breaks a tracker cycle."""
    import requests
    get = get or (lambda url, params: requests.get(url, params=params, timeout=15))
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        r = get(url, {"offset": offset, "timeout": 0})
        data = r.json()
        return data.get("result", []) if data.get("ok") else []
    except Exception:
        return []


def make_io(token: str):
    """Build the (send, answer_cb) callables bound to the live bot token."""
    import requests

    def send(chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            import json as _json
            payload["reply_markup"] = _json.dumps(reply_markup)
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data=payload, timeout=15)
        except Exception:
            pass

    def answer_cb(cq_id, text=""):
        try:
            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                          data={"callback_query_id": cq_id, "text": text},
                          timeout=15)
        except Exception:
            pass

    return send, answer_cb
