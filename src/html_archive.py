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

import re
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

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


def _hero_tokens(state: dict) -> dict:
    tokens = {
        "__HERO_MATCH__":       "—",
        "__HERO_META__":        "World Cup 2026",
        "__HERO_WIN__":         "Match data loading…",
        "__HERO_LEADER__":      "—",
        "__HERO_LEADER_DESC__": "Title odds loading…",
        "__MATCH_COUNT__":      "World Cup 2026",
    }

    last = state.get("last_result") or {}
    if last.get("home") and last.get("away"):
        home, away = str(last["home"]), str(last["away"])
        hg, ag = int(last.get("home_goals", 0)), int(last.get("away_goals", 0))
        tokens["__HERO_MATCH__"] = (
            f'{escape(home)} <span class="vs">vs</span> {escape(away)}')
        meta_bits = []
        if last.get("date"):
            meta_bits.append(_fmt_day_short(str(last["date"])))
        if last.get("venue"):
            meta_bits.append(str(last["venue"]))
        tokens["__HERO_META__"] = escape(" · ".join(meta_bits)) or "World Cup 2026"
        if hg > ag:
            tokens["__HERO_WIN__"] = escape(f"{home} won {hg}-{ag}")
        elif ag > hg:
            tokens["__HERO_WIN__"] = escape(f"{away} won {ag}-{hg}")
        else:
            tokens["__HERO_WIN__"] = escape(f"Draw {hg}-{ag}")

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

    if finished:
        hg, ag = int(m.get("hg", 0)), int(m.get("ag", 0))
        hcls = " win" if hg > ag else ""
        acls = " win" if ag > hg else ""
        center = (f'<span class="sc">{hg}</span>'
                  f'<span class="dash">–</span><span class="sc">{ag}</span>')
        hit = m.get("hit")
        pill = (f'<span class="pill {"ok" if hit else "no"}">'
                f'{"✓" if hit else "✗"}</span>')
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


def _render_board(state: dict) -> str:
    board = state.get("board") or []
    if not board:
        return _render_days(state.get("days") or [])
    blocks = []
    for i, day in enumerate(sorted(board, key=lambda d: d["date"], reverse=True)):
        open_attr = " open" if i == 0 else ""
        cards = "".join(_match_card(m) for m in day.get("matches", []))
        blocks.append(
            f'<details data-day="{escape(day["date"])}"{open_attr}>'
            f'<summary>{escape(_fmt_day_long(day["date"]))}</summary>'
            f'<div class="cards">{cards}</div></details>')
    return "".join(blocks)


def _render_standings(state: dict) -> str:
    groups = state.get("groups") or {}
    if not groups:
        return ""
    tables = []
    for g in sorted(groups):
        rows = groups[g]
        body = "".join(
            f'<tr class="{"qual" if n < 2 else ""}">'
            f'<td class="t-team">{escape(str(r["team"]))}</td>'
            f'<td>{r["played"]}</td><td class="t-pts">{r["points"]}</td>'
            f'<td>{r["gd"]:+d}</td><td>{r["gf"]}</td><td>{r["ga"]}</td></tr>'
            for n, r in enumerate(rows))
        tables.append(
            f'<table class="gtable"><caption>Group {escape(g)}</caption>'
            f'<thead><tr><th class="t-team">Team</th><th>P</th><th>Pts</th>'
            f'<th>GD</th><th>GF</th><th>GA</th></tr></thead><tbody>{body}</tbody></table>')
    return (
        '<div class="section-head"><h2>Group standings</h2>'
        '<span class="count">P · Pts · GD · GF · GA</span></div>'
        f'<div class="standings">{"".join(tables)}</div>')


def render(state: dict, path) -> None:
    """Render the full standalone archive page to `path`. Driven by the
    structured `board` + `groups` when present (Option 3); falls back to the
    message-text rendering otherwise."""
    page = SHELL
    for token, value in _hero_tokens(state).items():
        page = page.replace(token, value)
    page = page.replace("__STANDINGS__", _render_standings(state))
    page = page.replace("__DAYS__", _render_board(state))
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")


SHELL = r"""<!DOCTYPE html>

<html lang="en">
<head>
<meta charset="utf-8"/>
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

    .score { display: grid; grid-template-rows: auto 1fr auto; gap: 8px; height: 100%; }
    .score .team-line { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 28px; letter-spacing: -0.02em; line-height: 1.05; margin-top: 8px; }
    .score .team-line .vs { color: rgba(255,255,255,0.55); margin: 0 6px; font-weight: 400; }
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
<div class="h-card dark">
<div class="score">
<div class="kicker">Most recent</div>
<div class="team-line" id="hero-match">__HERO_MATCH__</div>
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
__STANDINGS__
<div class="section-head">
<h2>Match log</h2>
<span class="count" id="match-count">__MATCH_COUNT__</span>
</div>
<main id="days">__DAYS__</main>
<section class="signup-grid" id="signup">
<div class="signup-pitch">
<div class="signup-pitch-inner">
<div class="kicker">Get the messages</div>
<h2>Match-day updates, on Telegram.</h2>
<p>Predictions before kickoff. Half-time score at the break. Results as they finish, recap at night.</p>
<div class="stats">
<div><strong>~7</strong>messages / match day</div>
<div><strong>/stop</strong>to opt out</div>
</div>
</div>
</div>
<div class="signup-cta-box">
<div class="cta-eyebrow">One tap</div>
<div class="cta-headline">Tap Start on <em>WcFifa2026tracker</em>.</div>
<div class="cta-sub">That's the whole signup. Telegram requires you to message the bot first so it's allowed to message you back. After you tap Start, you're on the list for the next match.</div>
<a class="tg-cta" href="https://t.me/Kipl26bot" rel="noopener" target="_blank">Start on Telegram</a>
<p class="fine">Send <code>/stop</code> in the chat anytime to leave, <code>/start</code> to rejoin. No phone number needed. No spam.</p>
</div>
</section>
<footer class="foot">
<span class="made">Built by <a href="https://github.com/kcln/wckcfifa2026-tracker" rel="noopener" target="_blank">KC Lakshminarasimham</a></span>
<span class="links">fifa.com · ESPN FC</span>
</footer>
</div>
</body>
</html>
"""
