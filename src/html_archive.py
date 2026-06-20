"""
html_archive.py — renders docs/index.html (the public GitHub Pages archive).

Replicates the ipl-tracker archive design exactly (the committed purple
"Every match. Every prediction." page): same inline CSS, hero grid with
most-recent + leader cards, collapsible match-day log, Telegram CTA, and
a fixed PT/CT/ET/IST time stack per article (KC's spec). Adapted from
cricket to World Cup data.

Public API
----------
render(state: dict, path) -> None

`render` is a pure function of `state` (no clock calls) so output is
deterministic and testable. The tracker rebuilds the page on every run.
Stdlib only — the CI runtime has no third-party deps.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from src import knockout
except ImportError:  # pragma: no cover
    from . import knockout

# Per KC: article timestamps show a fixed four-zone stack, in this order.
_WHEN_ZONES = (
    ("PT",  ZoneInfo("America/Los_Angeles")),
    ("CT",  ZoneInfo("America/Chicago")),
    ("ET",  ZoneInfo("America/New_York")),
    ("IST", ZoneInfo("Asia/Kolkata")),
)

TOURNAMENT_DAYS = 39  # Jun 11 – Jul 19, 2026

# type -> (tag css class, label) — mirrors the IPL tag palette
_TAGS = {
    "morning_brief":  ("morning", "Morning brief"),
    "post_match":     ("result",  "Match result"),
    "half_time":      ("phase",   "Half-time"),
    "daily_recap":    ("recap",   "Day recap"),
    "bracket_update": ("phase",   "Bracket update"),
    "champion_recap": ("recap",   "Champion recap"),
}

# "Home 2-1 Away  ✓  (Prediction: X)" — possibly indented (recap lines)
_RESULT_RE = re.compile(r"^(\s*)(.+?) (\d+)\s*-\s*(\d+) (.+?)(\s\s.*)?$")
# "Prediction: PICK" terminated by "  |" or end of line (morning brief)
_PRED_RE = re.compile(r"^(.*?Prediction: )([^|]+?)(\s*\|.*|\s*)$")


def _fmt_day_long(date_iso: str) -> str:
    return datetime.strptime(date_iso, "%Y-%m-%d").strftime("%A, %B %-d, %Y")


def _fmt_day_short(date_iso: str) -> str:
    return datetime.strptime(date_iso, "%Y-%m-%d").strftime("%b %-d")


def _bold_result_line(line: str, indent: str, home: str, hg: int, ag: int,
                      away: str, tail: str) -> str:
    """Bold the winning team's name in a result line (IPL bolds winners)."""
    home_html, away_html = escape(home), escape(away)
    if hg > ag:
        home_html = f"<strong>{home_html}</strong>"
    elif ag > hg:
        away_html = f"<strong>{away_html}</strong>"
    return f"{escape(indent)}{home_html} {hg} - {ag} {away_html}{escape(tail or '')}"


def _render_text(body: str, msg_type: str) -> str:
    """Escape a (non-<pre>) body segment to HTML, applying the IPL bolding
    rules: winners bold in result lines, predicted pick bold in morning briefs."""
    out_lines = []
    for line in body.split("\n"):
        if msg_type in ("post_match", "daily_recap"):
            m = _RESULT_RE.match(line)
            if m:
                out_lines.append(_bold_result_line(
                    line, m.group(1), m.group(2), int(m.group(3)),
                    int(m.group(4)), m.group(5), m.group(6)))
                continue
        if msg_type == "morning_brief":
            m = _PRED_RE.match(line)
            if m:
                out_lines.append(
                    escape(m.group(1)) + f"<strong>{escape(m.group(2))}</strong>"
                    + escape(m.group(3)))
                continue
        out_lines.append(escape(line))
    return "\n".join(out_lines)


def _render_body(body: str, msg_type: str) -> str:
    """Render a message body, rendering any `<code>…</code>` block (the
    monospace standings table) as a real <pre> element so columns align on the
    page too."""
    parts = re.split(r"(<code>.*?</code>)", body, flags=re.S)
    out = []
    for part in parts:
        if part.startswith("<code>") and part.endswith("</code>"):
            inner = part[len("<code>"):-len("</code>")].strip("\n")
            out.append(f'<pre class="mono">{escape(inner)}</pre>')
        elif part:
            out.append(_render_text(part, msg_type))
    return "".join(out)


def _render_when(when_iso: str) -> str:
    """Four-zone time stack (PT/CT/ET/IST) from an ISO timestamp — the
    relevant match's kickoff. Messages without one get an empty stack."""
    if not when_iso:
        return '<span class="when"></span>'
    try:
        dt = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
    except ValueError:
        return '<span class="when"></span>'
    spans = "".join(
        f"<span>{dt.astimezone(tz).strftime('%-I:%M %p').lower().replace(' ', '')}"
        f" {label}</span>"
        for label, tz in _WHEN_ZONES
    )
    return f'<span class="when">{spans}</span>'


def _render_article(date_iso: str, idx: int, msg: dict) -> str:
    msg_type = str(msg.get("type", ""))
    tag_cls, label = _TAGS.get(msg_type, ("morning", msg_type.replace("_", " ").title()))
    generated = str(msg.get("generated_at", "") or "")
    gen_attr = f' data-generated="{escape(generated)}"' if generated else ""
    # The visible time is the match kickoff (KC's spec), not message time.
    when = _render_when(str(msg.get("kickoff_utc", "") or ""))
    body_html = _render_body(str(msg.get("body", "")), msg_type)
    return (
        f'<article data-type="{escape(msg_type)}"{gen_attr} '
        f'id="msg-{escape(date_iso)}-{escape(msg_type)}-{idx}">'
        f'<div class="meta"><span class="tag {tag_cls}">{escape(label)}</span>'
        f'{when}</div>'
        f'<div class="body">{body_html}</div></article>'
    )


def _render_days(days: list[dict]) -> str:
    """Newest day first; only the newest open; newest article first in a day."""
    ordered = sorted(days, key=lambda d: str(d.get("date", "")), reverse=True)
    blocks = []
    for i, day in enumerate(ordered):
        date_iso = str(day.get("date", ""))
        open_attr = " open" if i == 0 else ""
        messages = [m for m in (day.get("messages") or [])]
        articles = "".join(
            _render_article(date_iso, idx, m)
            for idx, m in reversed(list(enumerate(messages)))
        )
        blocks.append(
            f'<details data-day="{escape(date_iso)}"{open_attr}>'
            f"<summary>{escape(_fmt_day_long(date_iso))}</summary>"
            f"{articles}</details>"
        )
    return "".join(blocks)


def _featured_match(state: dict):
    """The match the hero should show: the LIVE one (latest kickoff) if any is
    in progress, otherwise the most recent finished result. Returns a dict with
    a `_live` flag, or None when there's nothing to show yet."""
    live = state.get("live") or []
    if live:
        return dict(live[-1], _live=True)
    last = state.get("last_result") or {}
    if last.get("home") and last.get("away"):
        return {**last, "_live": False}
    return None


def _live_payload(state: dict) -> dict:
    """Compact JSON the page polls (docs/live.json) to refresh the hero card in
    place without a full reload. Mirrors the fields _hero_tokens renders."""
    f = _featured_match(state)
    if not f:
        return {"live": False}
    return {
        "live":   bool(f["_live"]),
        "id":     str(f.get("id", "")),
        "home":   str(f["home"]),
        "away":   str(f["away"]),
        "hg":     int(f.get("hg", f.get("home_goals", 0))),
        "ag":     int(f.get("ag", f.get("away_goals", 0))),
        "status": str(f.get("status", "")),
        "clock":  str(f.get("clock", "")).strip(),
        "date":   str(f.get("date", "")),
        "venue":  str(f.get("venue", "")),
        "events": f.get("events") or [],
    }


def _hero_tokens(state: dict) -> dict:
    tokens = {
        "__HERO_KICKER__":      "Most recent",
        "__HERO_MATCH__":       "—",
        "__HERO_META__":        "World Cup 2026",
        "__HERO_WIN__":         "Match data loading…",
        "__HERO_LEADER__":      "—",
        "__HERO_LEADER_DESC__": "Title odds loading…",
        "__MATCH_COUNT__":      "World Cup 2026",
        "__HERO_SCORERS__":     "",
        "__REFRESH__":          "",
    }

    featured = _featured_match(state)
    if featured:
        home, away = str(featured["home"]), str(featured["away"])
        hg = int(featured.get("hg", featured.get("home_goals", 0)))
        ag = int(featured.get("ag", featured.get("away_goals", 0)))
        # Score lives in the headline team line; the old separate result line
        # is dropped (KC). Each token is its own span so the flex `gap` gives
        # even spacing on BOTH sides of every score — bare whitespace let the
        # score hug the team name while the dash had margin (lopsided).
        tokens["__HERO_MATCH__"] = (
            f'<span class="tm">{escape(home)}</span>'
            f'<span class="sc">{hg}</span>'
            f'<span class="vs">–</span>'
            f'<span class="sc">{ag}</span>'
            f'<span class="tm">{escape(away)}</span>')
        tokens["__HERO_SCORERS__"] = _events_html(featured.get("events") or [])
        tokens["__HERO_WIN__"] = ""
        meta_bits = []
        if featured.get("date"):
            meta_bits.append(_fmt_day_short(str(featured["date"])))
        if featured.get("venue"):
            meta_bits.append(str(featured["venue"]))
        tokens["__HERO_META__"] = escape(" · ".join(meta_bits)) or "World Cup 2026"
        if featured["_live"]:
            clk = ("Half-time" if featured.get("status") == "HT"
                   else str(featured.get("clock", "")).strip())
            suffix = f" · {escape(clk)}" if clk else ""
            tokens["__HERO_KICKER__"] = (
                f'<span class="livedot"></span> Live now{suffix}')
            # No <meta refresh>: the hero polls live.json client-side (see the
            # poll script) and updates in place, so the page is never frozen
            # between matches and never does a jarring full reload mid-match.

    title_odds = (state.get("bracket") or {}).get("title_odds") or {}
    if title_odds:
        leader, prob = max(title_odds.items(), key=lambda kv: kv[1])
        tokens["__HERO_LEADER__"] = escape(str(leader))
        tokens["__HERO_LEADER_DESC__"] = escape(
            f"{prob * 100:.1f}% title odds · ML model + Monte Carlo bracket")

    days = state.get("days") or []
    if days:
        tokens["__MATCH_COUNT__"] = f"Day {len(days)} of {TOURNAMENT_DAYS}"
    return tokens


# ---------------------------------------------------------------------------
# Structured rendering (Option 3): drive the page from state's board + groups,
# not from the Telegram message text.
# ---------------------------------------------------------------------------

_VENUE_COUNTRY = {
    "Atlanta": "USA", "Boston (Foxborough)": "USA", "Dallas (Arlington)": "USA",
    "Guadalajara (Zapopan)": "Mexico", "Houston": "USA", "Kansas City": "USA",
    "Los Angeles (Inglewood)": "USA", "Mexico City": "Mexico",
    "Miami (Miami Gardens)": "USA", "Monterrey (Guadalupe)": "Mexico",
    "New York/New Jersey (East Rutherford)": "USA", "Philadelphia": "USA",
    "San Francisco Bay Area (Santa Clara)": "USA", "Seattle": "USA",
    "Toronto": "Canada", "Vancouver": "Canada",
}


def _place(venue: str) -> str:
    if not venue:
        return ""
    c = _VENUE_COUNTRY.get(venue)
    return f"{venue}, {c}" if c else venue


def _pct(p: float) -> str:
    return f"{p * 100:.1f}%"


def _kick_chips(kickoff_utc: str) -> str:
    if not kickoff_utc:
        return ""
    try:
        dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    except ValueError:
        return ""
    chips = "".join(
        f'<span class="chip-time">'
        f'{dt.astimezone(tz).strftime("%-I:%M%p").lower()} {lbl}</span>'
        for lbl, tz in _WHEN_ZONES)
    return f'<div class="kick">{chips}</div>'


def _events_html(events: list) -> str:
    if not events:
        return ""
    rows = []
    for e in events:
        icon = "🟥" if e.get("kind") == "red" else "⚽"
        annot = {"own_goal": " <span class=\"og\">OG</span>",
                 "penalty": " <span class=\"og\">pen</span>"}.get(e.get("kind"), "")
        rows.append(
            f'<li><span class="ev-min">{escape(str(e.get("minute", "")))}</span> '
            f'<span class="ev-i">{icon}</span> {escape(str(e.get("player", "")))} '
            f'<span class="ev-team">{escape(str(e.get("team", "")))}</span>{annot}</li>')
    return f'<ul class="scorers">{"".join(rows)}</ul>'


def _match_card(m: dict) -> str:
    home, away = escape(str(m["home"])), escape(str(m["away"]))
    pred = m.get("pred") or {}
    pick = escape(str(pred.get("pick", "")))
    finished = m.get("status") == "FT"
    is_live = m.get("status") == "live"

    if finished or is_live:
        hg, ag = int(m.get("hg", 0)), int(m.get("ag", 0))
        center = (f'<span class="sc">{hg}</span>'
                  f'<span class="dash">–</span><span class="sc">{ag}</span>')
    if finished:
        hcls = " win" if hg > ag else ""
        acls = " win" if ag > hg else ""
        hit = m.get("hit")
        pill = (f'<span class="pill {"ok" if hit else "no"}">'
                f'{"✓" if hit else "✗"}</span>')
    elif is_live:
        hcls = acls = ""
        label = "Half-time" if m.get("ht") else (escape(str(m.get("clock", ""))) or "Live")
        pill = f'<span class="pill live"><span class="livedot"></span>{label}</span>'
    else:
        center = '<span class="vsbig">vs</span>'
        hcls = acls = ""
        pill = '<span class="pill soon">upcoming</span>'

    bar = ""
    if pred:
        h, d, a = pred.get("home", 0), pred.get("draw", 0), pred.get("away", 0)
        # Each label box is as wide as its bar segment and centre-aligned, so
        # the label sits centred over its own segment.
        bar = (
            f'<div class="oddsbar" title="{home} {_pct(h)} · Draw {_pct(d)} · {away} {_pct(a)}">'
            f'<span class="seg sh" style="width:{h*100:.1f}%"></span>'
            f'<span class="seg sd" style="width:{d*100:.1f}%"></span>'
            f'<span class="seg sa" style="width:{a*100:.1f}%"></span></div>'
            f'<div class="oddskey">'
            f'<span style="flex-basis:{h*100:.1f}%">{home} {_pct(h)}</span>'
            f'<span style="flex-basis:{d*100:.1f}%">Draw {_pct(d)}</span>'
            f'<span style="flex-basis:{a*100:.1f}%">{away} {_pct(a)}</span></div>')

    foot_bits = []
    loc = _place(str(m.get("venue", "")))
    if loc:
        foot_bits.append(f'📍 {escape(loc)}')
    foot = f'<div class="mc-foot">{" · ".join(foot_bits)}</div>' if foot_bits else ""
    kick = _kick_chips(str(m.get("kickoff_utc", "")))

    # Bold the pick only when the prediction turned out right.
    pick_html = (f'<strong class="hit">{pick}</strong>'
                 if (finished and m.get("hit")) else f'<span class="miss">{pick}</span>')

    return (
        f'<div class="mcard">'
        f'<div class="mc-top">'
        f'<span class="tm{hcls}">{home}</span>'
        f'<span class="mid">{center}</span>'
        f'<span class="tm{acls}">{away}</span></div>'
        f'<div class="mc-pred">Prediction: {pick_html} {pill}</div>'
        f'{bar}{_events_html(m.get("events") or [])}{kick}{foot}</div>')


def _signup(sec_id: str) -> str:
    """The Telegram sign-up CTA — just the call-to-action box (the dark
    "Match-day updates" pitch panel was removed per KC). Rendered both at the
    top of the page and the bottom; `sec_id` keeps the two ids unique."""
    return (
        f'<section class="signup-grid solo" id="{sec_id}">'
        '<div class="signup-cta-box"><div class="cta-eyebrow">One tap</div>'
        '<div class="cta-headline">Tap Start on <em>WcFifa2026tracker</em>.</div>'
        "<div class=\"cta-sub\">That's the whole signup. Telegram requires you "
        'to message the bot first so it\'s allowed to message you back. New '
        "sign-ups are approved, then match updates start with the next match."
        "</div>"
        '<a class="tg-cta" href="https://t.me/Kipl26bot" rel="noopener" '
        'target="_blank">Start on Telegram</a>'
        '<p class="fine">Send <code>/stop</code> in the chat anytime to leave, '
        '<code>/start</code> to rejoin. No phone number needed. No spam.</p>'
        '</div></section>')


def _tools(scope: str) -> str:
    """Expand-all / Collapse-all buttons for a section's collapsibles."""
    return (
        '<div class="sec-tools">'
        f'<button type="button" data-act="expand" data-scope="{scope}">Expand all</button>'
        f'<button type="button" data-act="collapse" data-scope="{scope}">Collapse all</button>'
        '</div>')


def _order_day_matches(matches: list) -> list:
    """Order a day's match cards by relevance (KC's spec):

    - while any match is live: live first (earliest kickoff = closest to the
      final whistle on top), then upcoming soonest-first, then finished at the
      bottom (most recent first);
    - when nothing is live (gaps between games, and every past day): pure
      reverse chronological, latest kickoff on top.
    """
    def ko(m):
        return (m.get("kickoff_utc") or "", str(m.get("id", "")))

    live = [m for m in matches if m.get("status") == "live"]
    if not live:
        return sorted(matches, key=ko, reverse=True)
    done = [m for m in matches if m.get("status") == "FT"]
    upcoming = [m for m in matches if m.get("status") not in ("live", "FT")]
    return (sorted(live, key=ko)                    # closest to finishing on top
            + sorted(upcoming, key=ko)              # soonest next first
            + sorted(done, key=ko, reverse=True))   # most recently finished first


def _render_board_days(state: dict) -> str:
    """Day cards (board), newest first. The newest day (today's status) is open
    on first render; the rest are collapsed."""
    board = state.get("board") or []
    if not board:
        return _render_days(state.get("days") or [])
    blocks = []
    for i, day in enumerate(sorted(board, key=lambda d: d["date"], reverse=True)):
        open_attr = " open" if i == 0 else ""   # today's status opens by default
        cards = "".join(_match_card(m) for m in _order_day_matches(day.get("matches", [])))
        blocks.append(
            f'<details class="day" data-day="{escape(day["date"])}"{open_attr}>'
            f'<summary>{escape(_fmt_day_long(day["date"]))}</summary>'
            f'<div class="cards">{cards}</div></details>')
    return "".join(blocks)


def _kick_pt_short(kickoff_utc: str) -> str:
    """Compact single-zone kickoff label for a schedule box, e.g. '1:00pm PT'."""
    if not kickoff_utc:
        return ""
    try:
        dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    except ValueError:
        return ""
    pt = dt.astimezone(_WHEN_ZONES[0][1])              # America/Los_Angeles
    hour = (pt.hour % 12) or 12
    return f'{hour}:{pt.strftime("%M")}{pt.strftime("%p").lower()} PT'


def _fmt_day_col(date_iso: str) -> str:
    """Short day-column header, e.g. 'Wed Jun 17'."""
    try:
        return datetime.strptime(date_iso, "%Y-%m-%d").strftime("%a %b %-d")
    except ValueError:
        return date_iso


def _sched_box(m: dict) -> str:
    """One compact match box for the by-day Schedule strip: teams, score-or-
    kickoff, live dot + minute while in progress, and the venue. No scorers,
    no prediction bar (KC)."""
    home, away = escape(str(m["home"])), escape(str(m["away"]))
    st = m.get("status")
    if st in ("FT", "live"):
        hg, ag = int(m.get("hg") or 0), int(m.get("ag") or 0)
        teams = (f'{home}<span class="dsc">{hg}</span>'
                 f'<span class="dvs">–</span><span class="dsc">{ag}</span>{away}')
    else:
        teams = f'{home}<span class="dvs">vs</span>{away}'

    if st == "live":
        clk = escape(str(m.get("clock", "")).strip() or "Live")
        meta = f'<span class="livedot"></span>{clk}'
    elif st == "FT":
        meta = "Full time"
    else:
        meta = escape(_kick_pt_short(str(m.get("kickoff_utc", ""))))
    loc = escape(_place(str(m.get("venue", ""))))
    loc_html = f'<div class="dbox-loc">📍 {loc}</div>' if loc else ""
    cls = {"FT": "done", "live": "live"}.get(st, "soon")
    return (
        f'<div class="dbox {cls}" data-mid="{escape(str(m.get("id", "")))}">'
        f'<div class="dbox-teams">{teams}</div>'
        f'<div class="dbox-meta">{meta}</div>{loc_html}</div>')


KO_START = "2026-06-28"   # knockouts begin: strip covers the group days before this


def _render_schedule(state: dict, today: str | None = None) -> str:
    """One horizontally-scrollable Schedule: group-stage day columns (Jun 11 →
    Jun 27) flow straight into the knockout bracket on the right — both visible
    at once, no date gate. (`today` kept for signature compatibility.)"""
    strip = _strip_columns(state)
    bracket = _bracket_html(state)
    if not strip and not bracket:
        return ""
    divider = ('<div class="sched-div"><span>Knockouts</span></div>'
               if strip and bracket else "")
    note = ('<div class="sched-note"><em>Italic</em> bracket teams are projected '
            'from the live table; once a team <span class="qlk">clinches</span> '
            'a Round-of-32 berth the slot drops the others and shows only the '
            'qualified team. Slots lock fully when the group is decided.</div>'
            if bracket else "")
    return (
        '<details class="section" id="schedule">'
        '<summary><span class="sec-h">Schedule</span>'
        '<span class="sec-count">Full tournament</span></summary>'
        f'<div class="sec-body"><div class="daystrip">'
        f'{strip}{divider}{bracket}</div>{note}</div></details>')


def _strip_columns(state: dict) -> str:
    """Group-stage day columns (dates before the knockouts begin), current day
    highlighted. Knockout days (Jun 28+) live in the bracket, not here."""
    sched = state.get("schedule") or []
    days = sorted((d for d in sched if d.get("matches")
                   and (d.get("date") or "") < KO_START),
                  key=lambda d: d.get("date") or "")
    if not days:
        return ""

    def has(day, st):
        return any(m.get("status") == st for m in day["matches"])
    live_days = [d["date"] for d in days if has(d, "live")]
    ft_days = [d["date"] for d in days if has(d, "FT")]
    cur = (max(live_days) if live_days
           else max(ft_days) if ft_days else days[0]["date"])

    cols = []
    for d in days:
        date = d.get("date") or ""
        td = " is-today" if date == cur else ""
        boxes = "".join(_sched_box(m) for m in sorted(
            d["matches"], key=lambda x: (x.get("kickoff_utc") or "",
                                         str(x.get("id", "")))))
        cols.append(
            f'<div class="daycol{td}" data-date="{escape(date)}">'
            f'<div class="daycol-head">{escape(_fmt_day_col(date))}</div>'
            f'{boxes}</div>')
    return "".join(cols)


def _bracket_positions(by_id: dict) -> dict:
    """Vertical position per knockout match from the feeder tree, so the bracket
    columns line up (each tie sits between the two it's fed by). Leaves (R32) get
    sequential slots; an internal tie sits at the mean of its feeders."""
    pos: dict = {}
    counter = [0]

    def feeders(mid):
        m = by_id[mid]
        out = []
        for tok in (str(m.get("home", "")), str(m.get("away", ""))):
            if tok[:1] == "W" and tok[1:].isdigit() and tok[1:] in by_id:
                out.append(tok[1:])
        return out

    def visit(mid):
        ks = feeders(mid)
        if not ks:
            pos[mid] = counter[0]
            counter[0] += 1
            return pos[mid]
        ps = [visit(k) for k in ks]
        pos[mid] = sum(ps) / len(ps)
        return pos[mid]

    final = next((mid for mid, m in by_id.items()
                  if m.get("stage") == "final"), None)
    if final:
        visit(final)
    for mid in by_id:                      # 3rd place / anything disconnected
        pos.setdefault(mid, 1e9)
    return pos


def _slot_html(token: str, groups: dict, clinched: set,
               winners: dict, losers: dict) -> str:
    """Safe HTML label for a knockout slot. A still-projected group slot shows
    the whole group order in standings order — but once any team in that group
    clinches, it collapses to just the qualified team(s), locked solid (.qlk),
    dropping the still-contending names. Everything else falls back to the plain
    escaped slot_label."""
    t = (token or "").strip()
    is_group_slot = (len(t) >= 2 and t[0] in "12" and t[1:].isalpha()
                     and "/" not in t)
    if is_group_slot and not knockout.slot_locked(t, groups, winners, losers):
        rows = groups.get(t[1:]) or []
        if rows:
            qualified = [r for r in rows
                         if r.get("team") in (clinched or set())]
            if qualified:                  # someone's through -> show only them
                return " / ".join(
                    f'<span class="qlk">{escape(knockout.abbr(r.get("team", "")))}'
                    f'</span>' for r in qualified)
            return " / ".join(             # nobody yet -> full projected order
                escape(knockout.abbr(r.get("team", ""))) for r in rows)
    return escape(knockout.slot_label(t, groups, winners, losers))


def _bracket_box(m: dict, groups: dict, winners: dict, losers: dict,
                 clinched: set | None = None) -> str:
    clinched = clinched or set()
    ht, at = str(m.get("home", "")), str(m.get("away", ""))
    hl = _slot_html(ht, groups, clinched, winners, losers)
    al = _slot_html(at, groups, clinched, winners, losers)
    # Projected (live table) vs locked (group decided / feeder played).
    h_proj = not knockout.slot_locked(ht, groups, winners, losers)
    a_proj = not knockout.slot_locked(at, groups, winners, losers)
    st = m.get("status")
    played = st in ("FT", "live")
    hg, ag = int(m.get("hg") or 0), int(m.get("ag") or 0)
    if st == "live":
        clk = escape(str(m.get("clock", "")).strip() or "Live")
        tag = f'<div class="bkm-tag livet"><span class="livedot"></span>{clk}</div>'
    elif st == "FT":
        tag = '<div class="bkm-tag">Full time</div>'
    else:
        tag = (f'<div class="bkm-tag">'
               f'{escape(_kick_pt_short(str(m.get("kickoff_utc", ""))))}</div>')

    def row(label_html, sc, win, proj):
        s = f'<span class="bkm-sc">{sc}</span>' if played else ""
        wc = " win" if win else ""
        pc = " proj" if proj else ""
        return (f'<div class="bkm-row{wc}{pc}">'
                f'<span class="bkm-nm">{label_html}</span>{s}</div>')

    loc = escape(_place(str(m.get("venue", ""))))
    loc_html = f'<div class="bkm-loc">📍 {loc}</div>' if loc else ""
    cls = " live" if st == "live" else ""
    return (f'<div class="bkm{cls}">{tag}'
            f'{row(hl, hg, st == "FT" and hg > ag, h_proj)}'
            f'{row(al, ag, st == "FT" and ag > hg, a_proj)}{loc_html}</div>')


def _bracket_html(state: dict) -> str:
    """Classic horizontal knockout bracket (R32 → Final) as one inline flex
    block, appended to the right of the group strip. Slot tokens resolve to
    live country codes; each tie shows its venue. Empty string if no knockout
    data yet."""
    sched = state.get("schedule") or []
    groups = state.get("groups") or {}
    ko = [{**m, "date": d.get("date")} for d in sched
          for m in d.get("matches", []) if m.get("stage") not in ("group", None)]
    if not ko:
        return ""
    by_id = {str(m["id"]): m for m in ko}
    pos = _bracket_positions(by_id)
    winners, losers = {}, {}                # resolved as knockout results land
    clinched = knockout.clinched_set(groups, sched)

    rounds: dict = {}
    for m in ko:
        rounds.setdefault(m.get("stage"), []).append(m)
    for st in rounds:
        rounds[st].sort(key=lambda x: pos.get(str(x["id"]), 0))

    def box(m):
        return _bracket_box(m, groups, winners, losers, clinched)

    def feeder_round(label, ms):
        pairs = ""
        for i in range(0, len(ms) - 1, 2):
            pairs += (f'<div class="bk-pair"><div class="bk-cell">{box(ms[i])}'
                      f'</div><div class="bk-cell">{box(ms[i + 1])}</div></div>')
        if len(ms) % 2:
            pairs += f'<div class="bk-pair"><div class="bk-cell">{box(ms[-1])}</div></div>'
        return (f'<div class="bk-rnd bk-feeder"><div class="rlabel">{label}</div>'
                f'{pairs}</div>')

    def plain_round(label, ms):
        cells = "".join(f'<div class="bk-cell">{box(m)}</div>' for m in ms)
        return f'<div class="bk-rnd"><div class="rlabel">{label}</div>{cells}</div>'

    cols = (feeder_round("Round of 32", rounds.get("R32", []))
            + feeder_round("Round of 16", rounds.get("R16", []))
            + feeder_round("Quarter-finals", rounds.get("QF", []))
            + feeder_round("Semi-finals", rounds.get("SF", []))
            + plain_round("Final", rounds.get("final", [])))
    third = rounds.get("3rd", [])
    third_html = (f'<div class="bk-rnd bk-third"><div class="rlabel">Third place'
                  f'</div><div class="bk-cell">{box(third[0])}</div></div>'
                  ) if third else ""
    return f'<div class="bk">{cols}{third_html}</div>'


def _render_matchlog(state: dict) -> str:
    """The whole Match-log section. Open on first render (with today's day
    expanded inside); expand/collapse-all toggles every day."""
    count = ""
    if state.get("days"):
        count = (f'<span class="sec-count">Day {len(state["days"])} '
                 f'of {TOURNAMENT_DAYS}</span>')
    return (
        '<details class="section" open>'
        f'<summary><span class="sec-h">Match log</span>{count}</summary>'
        f'<div class="sec-body">{_tools("days")}'
        f'<main id="days">{_render_board_days(state)}</main></div></details>')


def _render_standings(state: dict) -> str:
    """The whole Group-standings section: collapsible, definitions legend,
    expand/collapse-all, and per-group collapsible tables (all collapsed)."""
    groups = state.get("groups") or {}
    if not groups:
        return ""
    clinched = knockout.clinched_set(groups, state.get("schedule") or [])
    grps = []
    for g in sorted(groups):
        body = "".join(
            f'<tr class="{"qual" if n < 2 else ""}">'
            f'<td class="t-team">{escape(str(r["team"]))}'
            f'{" <span class=\"qb\">Q</span>" if r["team"] in clinched else ""}</td>'
            f'<td>{r["played"]}</td><td class="t-pts">{r["points"]}</td>'
            f'<td>{r["gd"]:+d}</td><td>{r["gf"]}</td><td>{r["ga"]}</td></tr>'
            for n, r in enumerate(groups[g]))
        grps.append(
            f'<details class="grp"><summary>Group {escape(g)}</summary>'
            f'<table class="gtable">'
            f'<thead><tr><th class="t-team">Team</th><th>P</th><th>Pts</th>'
            f'<th>GD</th><th>GF</th><th>GA</th></tr></thead>'
            f'<tbody>{body}</tbody></table></details>')
    legend = ('<div class="legend">P = Played · Pts = Points · '
              'GD = Goal Difference · GF = Goals For · GA = Goals Against · '
              '<span class="qb">Q</span> = Qualified for Round of 32</div>')
    return (
        '<details class="section" id="standings">'
        '<summary><span class="sec-h">Group standings</span></summary>'
        f'<div class="sec-body">{legend}{_tools("groups")}'
        f'<div class="standings">{"".join(grps)}</div></div></details>')


def render(state: dict, path, today: str | None = None) -> None:
    """Render the full standalone archive page to `path`. Driven by the
    structured `board` + `groups` when present (Option 3); falls back to the
    message-text rendering otherwise. `today` (PT date) flips the Schedule from
    the group-stage strip to the knockout bracket on Jun 28."""
    page = SHELL
    for token, value in _hero_tokens(state).items():
        page = page.replace(token, value)
    page = page.replace("__STANDINGS__", _render_standings(state))
    page = page.replace("__MATCHLOG__", _render_matchlog(state))
    page = page.replace("__SCHEDULE__", _render_schedule(state, today))
    page = page.replace("__SIGNUP_TOP__", _signup("signup-top"))
    page = page.replace("__SIGNUP_BOTTOM__", _signup("signup"))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    # Sibling payload the hero polls to refresh in place (see the poll script).
    (out.parent / "live.json").write_text(
        json.dumps(_live_payload(state)), encoding="utf-8")


SHELL = r"""<!DOCTYPE html>

<html lang="en">
<head>
<meta charset="utf-8"/>
__REFRESH__
<title>World Cup 2026 — Daily tracker · KC Lakshminarasimham</title>
<meta content="width=device-width, initial-scale=1" name="viewport"/>
<meta content="#F8F5F1" name="theme-color"/>
<meta content="A machine-curated World Cup 2026 tracker — predictions before kickoff, results after each match, a recap at night. Delivered daily on Telegram." name="description"/>
<meta content="World Cup 2026 · Daily tracker" property="og:title"/>
<meta content="Predictions before kickoff, results after each match, a recap at night. Delivered daily on Telegram." property="og:description"/>
<link href="https://fonts.googleapis.com" rel="preconnect"/>
<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&amp;family=Work+Sans:wght@400;500;600&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap" rel="stylesheet"/>
<style>
    :root {
      --bg:           #F8F5F1;
      --card:         #FFFFFF;
      --card-2:       #FAF8F5;
      --brown:        #3F2A26;
      --brown-2:      #5A3E37;
      --brown-soft:   rgba(63,42,38,0.08);
      --brown-hair:   rgba(63,42,38,0.14);
      --ink:          #1F1612;
      --ink-2:        #3D2E27;
      --ink-soft:     rgba(31,22,18,0.62);
      --ink-faint:    rgba(31,22,18,0.40);
      --hair:         rgba(31,22,18,0.10);
      --hair-soft:    rgba(31,22,18,0.06);
      --p-50:  #FAF5FF;  --p-100: #F3E8FF;  --p-200: #E9D5FF;
      --p-300: #D8B4FE;  --p-400: #C084FC;  --p-500: #A855F7;
      --p-600: #9333EA;  --p-700: #7E22CE;  --p-800: #6B21A8;  --p-900: #581C87;
      --radius-lg: 24px;  --radius-md: 16px;  --radius-sm: 10px;
      --shadow-sm: 0 1px 2px rgba(31,22,18,0.05);
      --shadow-md: 0 1px 2px rgba(31,22,18,0.04), 0 8px 24px -8px rgba(31,22,18,0.10);
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { -webkit-font-smoothing: antialiased; }
    body { background: var(--bg); color: var(--ink); font-family: 'Work Sans', system-ui, sans-serif; font-weight: 400; min-height: 100vh; }
    a { color: inherit; text-decoration: none; }

    .wrap { max-width: 1080px; margin: 0 auto; padding: 0 24px; }

    nav.bar { display: flex; align-items: center; justify-content: space-between; padding: 28px 0; }
    nav .mark {
      display: inline-flex; align-items: center; justify-content: center;
      width: 44px; height: 44px;
      background: linear-gradient(135deg, var(--p-400), var(--p-800));
      border-radius: 10px;
      padding: 6px;
      box-shadow: 0 4px 16px rgba(126,34,206,0.25);
      transition: transform 0.15s, box-shadow 0.15s;
    }
    nav .mark:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(126,34,206,0.35); }
    nav .mark img { width: 100%; height: 100%; object-fit: contain; display: block; }
    nav .live { font-family: 'Work Sans', sans-serif; font-weight: 600; font-size: 13px; color: var(--ink); padding: 9px 16px; background: var(--card); border-radius: 100px; box-shadow: var(--shadow-sm); transition: all 0.15s; display: inline-flex; align-items: center; gap: 8px; }
    nav .live .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--p-600); animation: pulse 1.6s ease-in-out infinite; }
    @keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(147,51,234,0.6); } 50% { box-shadow: 0 0 0 6px rgba(147,51,234,0); } }
    nav .live:hover { background: var(--brown); color: var(--card); }
    nav .live:hover .dot { background: var(--p-400); }

    .hero-grid { display: grid; grid-template-columns: 2fr 1fr; grid-template-rows: auto auto; gap: 16px; margin-top: 8px; }
    .h-card { background: var(--card); border-radius: var(--radius-lg); padding: 32px; box-shadow: var(--shadow-md); border: 1px solid var(--hair-soft); }
    .h-card.dark { background: var(--brown); color: var(--card); }
    .h-card .kicker { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 18px; }
    .h-card.dark .kicker { color: rgba(255,255,255,0.72); }
    .h-card h1 { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: clamp(40px, 5.5vw, 64px); line-height: 1.0; letter-spacing: -0.025em; }
    .h-card h1 .grad { background: linear-gradient(135deg, var(--p-400), var(--p-800)); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
    .h-card .lead { margin-top: 18px; color: var(--ink-soft); font-size: 16px; line-height: 1.6; max-width: 52ch; }

    .score { display: flex; flex-direction: column; gap: 8px; height: 100%; }
    .score .team-line { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 0.34em; font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 28px; letter-spacing: -0.02em; line-height: 1.15; margin-top: 8px; }
    .score .team-line .sc { font-variant-numeric: tabular-nums; }
    .score .team-line .vs { color: rgba(255,255,255,0.55); font-weight: 400; }
    .score .scorers { margin: 2px 0 0; }
    .score .scorers li { color: rgba(255,255,255,0.82); font-size: 12px; }
    .score .scorers .ev-min, .score .scorers .ev-team, .score .scorers .og { color: rgba(255,255,255,0.5); }
    .score .result { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.20em; text-transform: uppercase; color: rgba(255,255,255,0.84); margin-top: auto; }
    .score .result .win { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 14px; letter-spacing: 0; text-transform: none; display: block; margin-top: 4px; color: var(--card); }

    .stat .v { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 56px; letter-spacing: -0.03em; line-height: 1; margin: 10px 0 6px; color: var(--p-700); }
    .stat .desc { font-size: 13px; color: var(--ink-soft); line-height: 1.5; }

    .section-head { margin: 56px 0 18px; display: flex; align-items: center; justify-content: space-between; }
    .section-head h2 { font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 22px; letter-spacing: -0.018em; }
    .section-head .count { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-faint); }

    /* ---- Option 3: structured standings tables + match cards ---- */
    .standings { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 16px; }
    .gtable { width: 100%; border-collapse: collapse; background: var(--card); border-radius: var(--radius-md); overflow: hidden; box-shadow: var(--shadow-sm); border: 1px solid var(--hair-soft); font-size: 13px; }
    .gtable caption { text-align: left; font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 14px; padding: 13px 14px 7px; color: var(--ink); }
    .gtable th { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); font-weight: 500; padding: 6px 8px; text-align: right; border-bottom: 1px solid var(--hair-soft); }
    .gtable th.t-team, .gtable td.t-team { text-align: left; }
    .gtable td { padding: 8px; text-align: right; border-bottom: 1px solid var(--hair-soft); color: var(--ink-2); font-variant-numeric: tabular-nums; }
    .gtable tbody tr:last-child td { border-bottom: 0; }
    .gtable td.t-team { font-weight: 600; color: var(--ink); }
    .gtable td.t-pts { font-weight: 700; color: var(--p-700); }
    .gtable tr.qual { background: var(--p-50); }
    .gtable tr.qual td.t-team { box-shadow: inset 3px 0 0 var(--p-500); }
    .qb { display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em; line-height: 1; color: var(--card); background: var(--p-600); border-radius: 4px; padding: 2px 5px; margin-left: 7px; vertical-align: middle; }
    .legend .qb { margin-left: 0; }

    main#days .cards { display: grid; gap: 12px; padding: 6px 0 10px; }
    .mcard { background: var(--card-2); border: 1px solid var(--hair-soft); border-radius: var(--radius-md); padding: 15px 16px; }
    .mc-top { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 10px; }
    .mc-top .tm { font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 16px; letter-spacing: -0.01em; }
    .mc-top .tm:first-child { text-align: right; }
    .mc-top .tm.win { color: var(--p-700); }
    .mc-top .mid { font-family: 'Outfit', sans-serif; font-weight: 800; text-align: center; white-space: nowrap; }
    .mc-top .sc { font-size: 22px; }
    .mc-top .dash { margin: 0 5px; color: var(--ink-faint); }
    .mc-top .vsbig { font-size: 12px; color: var(--ink-faint); font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; }
    .mc-pred { margin-top: 10px; font-size: 13px; color: var(--ink-soft); display: flex; align-items: center; gap: 8px; }
    .mc-pred .hit { color: var(--ink); font-weight: 700; }
    .mc-pred .miss { color: var(--ink-soft); font-weight: 400; }
    .pill { font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 2px 8px; border-radius: 100px; letter-spacing: 0.04em; }
    .pill.ok { background: #DCFCE7; color: #15803D; }
    .pill.no { background: #FEE2E2; color: #B91C1C; }
    .pill.soon { background: var(--p-100); color: var(--p-700); }
    .pill.live { background: #FEE2E2; color: #B91C1C; display: inline-flex; align-items: center; gap: 5px; }
    .livedot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #DC2626; animation: livepulse 1.4s ease-in-out infinite; }
    #hero-kicker .livedot { background: #F87171; vertical-align: middle; margin-right: 4px; }
    @keyframes livepulse { 0%,100% { opacity: 1; box-shadow: 0 0 0 0 rgba(220,38,38,0.5); } 50% { opacity: 0.6; box-shadow: 0 0 0 5px rgba(220,38,38,0); } }
    .oddsbar { display: flex; height: 6px; border-radius: 4px; overflow: hidden; margin: 11px 0 5px; }
    .oddsbar .seg.sh { background: var(--p-600); }
    .oddsbar .seg.sd { background: var(--ink-faint); }
    .oddsbar .seg.sa { background: var(--p-300); }
    .oddskey { display: flex; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--ink-faint); }
    .oddskey span { flex-grow: 0; flex-shrink: 0; min-width: 0; text-align: center; white-space: nowrap; overflow: visible; }
    .scorers { list-style: none; margin: 11px 0 0; padding: 0; display: grid; gap: 4px; }
    .scorers li { font-size: 13px; color: var(--ink-2); }
    .scorers .ev-min { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--ink-faint); display: inline-block; min-width: 38px; }
    .scorers .ev-team { color: var(--ink-faint); font-size: 12px; }
    .scorers .og { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--ink-faint); text-transform: uppercase; }
    .kick { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 11px; }
    .chip-time { font-family: 'JetBrains Mono', monospace; font-size: 10px; background: var(--bg); color: var(--ink-soft); padding: 3px 7px; border-radius: 6px; }
    .mc-foot { margin-top: 9px; font-size: 12px; color: var(--ink-faint); }

    /* ---- collapsible sections + groups (default collapsed) ---- */
    details.section { background: var(--card); border: 1px solid var(--hair-soft); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); margin: 22px 0; overflow: hidden; }
    details.section > summary { list-style: none; cursor: pointer; display: flex; align-items: center; gap: 12px; padding: 20px 24px; }
    details.section > summary::-webkit-details-marker { display: none; }
    details.section > summary::after { content: '+'; font-family: 'JetBrains Mono', monospace; font-size: 18px; color: var(--ink-soft); margin-left: 14px; }
    details.section[open] > summary::after { content: '\2013'; }
    .sec-h { font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 22px; letter-spacing: -0.018em; color: var(--ink); margin-right: auto; }
    .sec-count { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-faint); }
    .sec-body { padding: 0 24px 22px; }
    .sec-tools { display: flex; gap: 8px; margin: 6px 0 14px; }
    .sec-tools button { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-soft); background: var(--bg); border: 1px solid var(--hair); border-radius: 100px; padding: 6px 13px; cursor: pointer; transition: all 0.12s; }
    .sec-tools button:hover { background: var(--p-100); color: var(--p-700); border-color: transparent; }
    /* Schedule — full tournament as a by-day, horizontally-scrollable strip */
    .daystrip { display: flex; align-items: flex-start; gap: 14px; overflow-x: auto; padding: 8px 2px 16px; scroll-behavior: smooth; }
    /* divider where the group strip flows into the knockout bracket */
    .sched-div { flex: 0 0 auto; align-self: stretch; display: flex; align-items: center; justify-content: center; border-left: 2px dashed var(--hair); margin: 0 4px; padding: 0 2px; }
    .sched-div span { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--p-700); writing-mode: vertical-rl; transform: rotate(180deg); }
    .daycol { flex: 0 0 auto; width: 212px; display: flex; flex-direction: column; gap: 10px; padding: 0 8px 10px; border-radius: var(--radius-md); }
    .daycol-head { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-faint); padding: 4px 0 8px; border-bottom: 1px solid var(--hair-soft); margin-bottom: 2px; }
    .daycol.is-today { background: rgba(168,85,247,0.06); }
    .daycol.is-today .daycol-head { color: var(--p-700); border-color: var(--p-400); }
    .dbox { background: var(--card); border: 1px solid var(--hair-soft); border-radius: var(--radius-sm); box-shadow: var(--shadow-sm); padding: 11px 13px; }
    .dbox.live { border-color: var(--p-400); box-shadow: 0 0 0 1px var(--p-400); }
    .dbox-teams { font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 13px; color: var(--ink); display: flex; flex-wrap: wrap; align-items: baseline; gap: 0 6px; line-height: 1.35; }
    .dbox-teams .dsc { font-weight: 800; }
    .dbox-teams .dvs { color: var(--ink-faint); font-weight: 400; font-size: 11px; }
    .dbox-meta { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.06em; color: var(--ink-soft); margin-top: 6px; display: flex; align-items: center; gap: 6px; }
    .dbox.live .dbox-meta { color: var(--p-700); }
    .dbox-loc { font-size: 11px; color: var(--ink-faint); margin-top: 4px; }
    /* Knockout bracket (Schedule, from Jun 28) — classic horizontal tree */
    .bk { display: flex; flex: 0 0 auto; overflow: visible; padding: 6px 4px 12px; }
    .bk-rnd { display: flex; flex-direction: column; justify-content: space-around; min-width: 156px; padding-top: 22px; position: relative; }
    .bk-rnd + .bk-rnd { margin-left: 42px; }
    .bk-rnd > .rlabel { position: absolute; top: 0; left: 2px; white-space: nowrap; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-faint); }
    .bk-cell { flex: 1; display: flex; align-items: center; position: relative; }
    .bk-cell .bkm { width: 100%; }
    .bk-rnd:not(:last-child) .bk-cell::after { content: ''; position: absolute; right: -21px; top: 50%; width: 21px; height: 2px; background: var(--hair-soft); }
    .bk-rnd:not(:first-child) .bk-cell::before { content: ''; position: absolute; left: -21px; top: 50%; width: 21px; height: 2px; background: var(--hair-soft); }
    .bk-pair { flex: 1; display: flex; flex-direction: column; justify-content: space-around; position: relative; }
    .bk-feeder .bk-pair::after { content: ''; position: absolute; right: -21px; top: 25%; bottom: 25%; width: 2px; background: var(--hair-soft); }
    .bk-feeder .bk-pair::before { content: ''; position: absolute; right: -42px; top: 50%; width: 21px; height: 2px; background: var(--hair-soft); }
    .bkm { background: var(--card); border: 1px solid var(--hair-soft); border-radius: 9px; box-shadow: var(--shadow-sm); overflow: hidden; }
    .bkm.live { border-color: var(--p-400); box-shadow: 0 0 0 1px var(--p-400); }
    .bkm-tag { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); padding: 3px 9px; border-bottom: 1px solid var(--hair-soft); background: var(--card-2); }
    .bkm-tag.livet { color: var(--p-700); display: flex; align-items: center; gap: 5px; }
    .bkm-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 9px; font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 12.5px; color: var(--ink-soft); }
    .bkm-row + .bkm-row { border-top: 1px solid var(--hair-soft); }
    .bkm-row.win { color: var(--p-700); font-weight: 800; }
    .bkm-row.proj .bkm-nm { color: var(--ink-faint); font-style: italic; font-weight: 500; }
    .bkm-nm { line-height: 1.3; word-spacing: -1px; }
    .qlk { font-style: normal; font-weight: 800; color: var(--p-700); }
    .qlk::after { content: " ✓"; font-size: 0.85em; }
    .bkm-sc { font-family: 'Outfit', sans-serif; font-weight: 800; color: var(--ink); }
    .bkm-loc { font-size: 10px; color: var(--ink-faint); padding: 5px 9px 7px; border-top: 1px solid var(--hair-soft); }
    .bk-third { justify-content: flex-start; }
    .sched-note { font-size: 11.5px; color: var(--ink-faint); margin: 8px 2px 0; }
    .sched-note em { font-style: italic; color: var(--ink-soft); }
    .bk-third > .rlabel { display: block; margin-bottom: 6px; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-faint); }
    .legend { font-size: 12.5px; color: var(--ink-soft); margin: 4px 0 2px; line-height: 1.6; }
    details.grp { border: 1px solid var(--hair-soft); border-radius: var(--radius-md); overflow: hidden; background: var(--card); height: fit-content; }
    details.grp > summary { list-style: none; cursor: pointer; font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 14px; padding: 13px 14px; display: flex; align-items: center; justify-content: space-between; color: var(--ink); }
    details.grp > summary::-webkit-details-marker { display: none; }
    details.grp > summary::after { content: '+'; font-family: 'JetBrains Mono', monospace; color: var(--ink-faint); }
    details.grp[open] > summary::after { content: '\2013'; }
    details.grp .gtable { border: 0; border-radius: 0; box-shadow: none; border-top: 1px solid var(--hair-soft); }

    main#days { display: block; }

    details.day { background: var(--card); border-radius: var(--radius-lg); border: 1px solid var(--hair-soft); box-shadow: var(--shadow-sm); margin-bottom: 14px; overflow: hidden; transition: box-shadow 0.2s; }
    details.day:hover { box-shadow: var(--shadow-md); }
    details.day > summary { list-style: none; cursor: pointer; padding: 22px 28px; display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center; }
    details.day > summary::-webkit-details-marker { display: none; }
    .day-head { font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 19px; letter-spacing: -0.015em; line-height: 1.2; }
    .day-sub { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.20em; text-transform: uppercase; color: var(--ink-faint); margin-top: 6px; }
    details.day > summary .toggle { width: 32px; height: 32px; background: var(--bg); border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; color: var(--ink-soft); font-family: 'JetBrains Mono', monospace; font-size: 16px; transition: transform 0.25s, background 0.15s, color 0.15s; }
    details.day[open] > summary .toggle { transform: rotate(45deg); background: var(--p-700); color: var(--card); }

    .day-body { padding: 0 28px 24px; }
    article { padding: 18px 0; border-top: 1px solid var(--hair-soft); display: grid; grid-template-columns: 160px 1fr; gap: 22px; align-items: start; }
    article:first-of-type { border-top: 1px solid var(--hair); }
    article .meta { display: flex; flex-direction: column; gap: 8px; }
    article .meta .tag { display: inline-block; align-self: flex-start; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; padding: 4px 10px; border-radius: 100px; }
    article .meta .tag.morning { color: var(--p-700); background: var(--p-100); }
    article .meta .tag.phase   { color: var(--p-800); background: var(--p-200); }
    article .meta .tag.result  { color: var(--card);  background: var(--p-700); }
    article .meta .tag.recap   { color: var(--card);  background: var(--brown); }
    article .meta .when { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.10em; text-transform: uppercase; color: var(--ink-faint); line-height: 1.7; }
    article .meta .when span { display: block; }
    article .body { font-family: 'Work Sans', sans-serif; font-size: 14.5px; line-height: 1.7; color: var(--ink-2); white-space: pre-wrap; }
    article .body strong { font-weight: 700; color: var(--p-800); }
    article .body pre.mono { font-family: 'JetBrains Mono', monospace; font-size: 12px; line-height: 1.55; white-space: pre; overflow-x: auto; background: var(--card-2); border: 1px solid var(--hair-soft); border-radius: 8px; padding: 10px 12px; margin: 8px 0; }

    .signup-grid { margin-top: 56px; display: grid; grid-template-columns: 5fr 7fr; gap: 16px; }
    .signup-grid.solo { grid-template-columns: 1fr; margin-top: 24px; }
    .signup-pitch { background: var(--brown); color: var(--card); border-radius: var(--radius-lg); padding: 36px 32px; position: relative; overflow: hidden; }
    .signup-pitch::before { content: ''; position: absolute; bottom: -50%; right: -30%; width: 160%; height: 200%; background: radial-gradient(circle, rgba(168,85,247,0.40) 0%, transparent 60%); pointer-events: none; }
    .signup-pitch-inner { position: relative; }
    .signup-pitch .kicker { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--p-300); margin-bottom: 18px; }
    .signup-pitch h2 { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: clamp(28px, 4vw, 42px); line-height: 1.05; letter-spacing: -0.022em; }
    .signup-pitch p { margin-top: 16px; color: rgba(255,255,255,0.72); font-size: 15px; line-height: 1.6; }
    .signup-pitch .stats { margin-top: 28px; display: flex; gap: 28px; flex-wrap: wrap; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.10); }
    .signup-pitch .stats div { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; color: rgba(255,255,255,0.55); }
    .signup-pitch .stats strong { display: block; font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 22px; letter-spacing: -0.012em; color: var(--card); margin-bottom: 4px; }

    .signup-cta-box { background: var(--card); border-radius: var(--radius-lg); padding: 40px 32px; box-shadow: var(--shadow-md); border: 1px solid var(--hair-soft); display: flex; flex-direction: column; justify-content: center; gap: 18px; }
    .signup-cta-box .cta-eyebrow { font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink-faint); }
    .signup-cta-box .cta-headline { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: clamp(22px, 2.6vw, 28px); letter-spacing: -0.018em; line-height: 1.15; color: var(--ink); }
    .signup-cta-box .cta-headline em { font-style: italic; font-weight: 900; color: var(--p-800); }
    .signup-cta-box .cta-sub { color: var(--ink-soft); font-size: 14.5px; line-height: 1.6; }
    a.tg-cta { margin-top: 6px; font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 15px; background: var(--brown); color: var(--card); padding: 16px 24px; border-radius: var(--radius-sm); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 10px; transition: all 0.15s; text-decoration: none; }
    a.tg-cta::before { content: ''; width: 18px; height: 18px; background: currentColor; -webkit-mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M9.04 15.32 8.86 19.6c.31 0 .45-.13.61-.29l1.47-1.4 3.05 2.23c.56.31.95.15 1.11-.51l2.01-9.42c.18-.83-.3-1.15-.86-.94L4.39 13.69c-.81.31-.79.76-.14.96l3.06.96 7.1-4.47c.33-.21.64-.09.39.13'/></svg>") center/contain no-repeat; mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><path d='M9.04 15.32 8.86 19.6c.31 0 .45-.13.61-.29l1.47-1.4 3.05 2.23c.56.31.95.15 1.11-.51l2.01-9.42c.18-.83-.3-1.15-.86-.94L4.39 13.69c-.81.31-.79.76-.14.96l3.06.96 7.1-4.47c.33-.21.64-.09.39.13'/></svg>") center/contain no-repeat; }
    a.tg-cta::after { content: '→'; font-size: 18px; transition: transform 0.2s; }
    a.tg-cta:hover { background: var(--p-700); }
    a.tg-cta:hover::after { transform: translateX(4px); }

    .fine { margin-top: 6px; font-size: 12px; color: var(--ink-faint); line-height: 1.55; }
    .fine code { background: var(--bg); padding: 2px 6px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
    .fine a { color: var(--brown); text-decoration: underline; text-underline-offset: 2px; }
    .fine a:hover { color: var(--p-700); }
    .fine a code { background: var(--p-100); color: var(--brown); }

    footer.foot { margin: 64px 0 56px; padding: 24px 28px; background: var(--card); border-radius: var(--radius-lg); border: 1px solid var(--hair-soft); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; }
    footer .made { font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 14px; letter-spacing: -0.005em; }
    footer .made a { background: linear-gradient(120deg, var(--p-100), var(--p-200)); color: var(--p-800); padding: 3px 10px; border-radius: 100px; font-weight: 600; }
    footer .links { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-faint); }

    @media (max-width: 800px) {
      .hero-grid { grid-template-columns: 1fr; }
      .signup-grid { grid-template-columns: 1fr; }
      article { grid-template-columns: 1fr; gap: 10px; }
    }
    @media (max-width: 540px) {
      .wrap { padding: 0 18px; }
      .h-card { padding: 24px; }
      .h-card h1 { font-size: 40px; }
      details.day > summary { padding: 18px 20px; }
      .day-body { padding: 0 20px 20px; }
      .signup-pitch, .signup-cta-box { padding: 28px 24px; }
    }
  </style>
</head>
<body>
<div class="wrap">
<nav class="bar">
<a aria-label="KC Lakshminarasimham" class="mark" href="https://github.com/kcln" rel="noopener" target="_blank">
<img alt="Simham lion mark" height="44" src="assets/lion-transparent.png" width="44"/>
</a>
<a class="live" href="https://www.espn.com/soccer/league/_/name/fifa.world" rel="noopener" target="_blank"><span class="dot"></span> Live scores →</a>
</nav>
<section class="hero-grid">
<div class="h-card" style="grid-row: span 2;">
<div class="kicker">World Cup 2026 · Daily tracker</div>
<h1>Every match.<br/>Every <span class="grad">prediction.</span></h1>
<p class="lead">A machine-curated record of every match day this tournament — a prediction before kickoff, a result after each match, a recap at night. Delivered daily on Telegram.</p>
</div>
<div class="h-card dark" id="live">
<div class="score">
<div class="kicker" id="hero-kicker">__HERO_KICKER__</div>
<div class="team-line" id="hero-match">__HERO_MATCH__</div>
<div id="hero-scorers">__HERO_SCORERS__</div>
<div class="result">
<span id="hero-meta">__HERO_META__</span>
<span class="win" id="hero-win">__HERO_WIN__</span>
</div>
</div>
</div>
<div class="h-card stat">
<div class="kicker">Leader</div>
<div class="v" id="hero-leader">__HERO_LEADER__</div>
<div class="desc" id="hero-leader-desc">__HERO_LEADER_DESC__</div>
</div>
</section>
__SIGNUP_TOP__
__STANDINGS__
__MATCHLOG__
__SCHEDULE__
__SIGNUP_BOTTOM__
<footer class="foot">
<span class="made">Built by <a href="https://github.com/kcln/wckcfifa2026-tracker" rel="noopener" target="_blank">KC Lakshminarasimham</a></span>
<span class="links">fifa.com · ESPN FC</span>
</footer>
</div>
<script>
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-act]');
    if (!b) return;
    var open = b.getAttribute('data-act') === 'expand';
    var sel = b.getAttribute('data-scope') === 'groups'
      ? 'details.grp' : 'details[data-day]';
    var root = b.closest('.section') || document;
    root.querySelectorAll(sel).forEach(function (d) { d.open = open; });
  });
</script>
<script>
  // Live hero: poll live.json and update the score card in place, so the slot
  // always shows the current live match (or the most recent result) and is
  // never frozen between page loads. live.json is a tiny static file on the
  // Pages CDN — cheap, same-origin, no API quota to exhaust.
  (function () {
    var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun',
                  'Jul','Aug','Sep','Oct','Nov','Dec'];
    function esc(s) {
      return String(s).replace(/[&<>"']/g, function (c) {
        return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
      });
    }
    function fmtDay(iso) {
      var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
      if (!m) return '';
      return MONTHS[parseInt(m[2], 10) - 1] + ' ' + parseInt(m[3], 10);
    }
    function set(id, html) {
      var el = document.getElementById(id);
      if (el) el.innerHTML = html;
    }
    function scorers(events) {
      if (!events || !events.length) return '';
      var rows = events.map(function (e) {
        var icon = e.kind === 'red' ? '🟥' : '⚽';
        var annot = e.kind === 'own_goal' ? ' <span class="og">OG</span>'
                  : e.kind === 'penalty' ? ' <span class="og">pen</span>' : '';
        return '<li><span class="ev-min">' + esc(e.minute || '') +
          '</span> <span class="ev-i">' + icon + '</span> ' +
          esc(e.player || '') + ' <span class="ev-team">' +
          esc(e.team || '') + '</span>' + annot + '</li>';
      });
      return '<ul class="scorers">' + rows.join('') + '</ul>';
    }
    function paint(d) {
      if (!d || !d.home || !d.away) return;
      if (d.live) {
        var clk = d.status === 'HT' ? 'Half-time' : (d.clock || '');
        set('hero-kicker', '<span class="livedot"></span> Live now' +
            (clk ? ' &middot; ' + esc(clk) : ''));
      } else {
        set('hero-kicker', 'Most recent');
      }
      // Each piece is its own span so the flex `gap` spaces both sides of every
      // score evenly (no bare-whitespace hugging the team name).
      set('hero-match',
          '<span class="tm">' + esc(d.home) + '</span>' +
          '<span class="sc">' + d.hg + '</span>' +
          '<span class="vs">&ndash;</span>' +
          '<span class="sc">' + d.ag + '</span>' +
          '<span class="tm">' + esc(d.away) + '</span>');
      set('hero-scorers', scorers(d.events));
      var bits = [];
      if (d.date)  bits.push(fmtDay(d.date));
      if (d.venue) bits.push(esc(d.venue));
      set('hero-meta', bits.join(' &middot; ') || 'World Cup 2026');
      set('hero-win', '');
      // Reuse the same poll to keep the live match's Schedule-strip box current
      // — no extra request, so the strip ticks live with zero added overhead.
      if (d.live && d.id) {
        var box = document.querySelector('.dbox[data-mid="' + d.id + '"]');
        if (box) {
          box.classList.remove('soon', 'done'); box.classList.add('live');
          var t = box.querySelector('.dbox-teams');
          if (t) t.innerHTML = esc(d.home) + '<span class="dsc">' + d.hg +
            '</span><span class="dvs">&ndash;</span><span class="dsc">' + d.ag +
            '</span>' + esc(d.away);
          var mt = box.querySelector('.dbox-meta');
          if (mt) mt.innerHTML = '<span class="livedot"></span>' +
            esc(d.status === 'HT' ? 'HT' : (d.clock || 'Live'));
        }
      }
    }
    function poll() {
      fetch('live.json?t=' + Date.now(), { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(paint)
        .catch(function () { /* keep last good render */ });
    }
    poll();
    setInterval(poll, 30000);
  })();
  // Schedule strip: centre the highlighted current day on load and whenever
  // the (collapsed-by-default) section is opened.
  (function () {
    function centre() {
      var strip = document.querySelector('.daystrip');
      if (!strip) return;
      var t = strip.querySelector('.daycol.is-today');
      if (t) strip.scrollLeft =
        t.offsetLeft - strip.clientWidth / 2 + t.clientWidth / 2;
    }
    centre();
    var sec = document.getElementById('schedule');
    if (sec) sec.addEventListener('toggle', function () {
      if (sec.open) centre();
    });
  })();
</script>
</body>
</html>
"""
