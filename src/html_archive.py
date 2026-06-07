"""
html_archive.py — renders docs/index.html (the public GitHub Pages archive)
from the tracker's state, styled with the KCL Editorial x Bauhaus brand.

Public API
----------
render(state: dict, path) -> None

`render` is a pure function of `state` (no clock calls) so output is
deterministic and testable. The tracker rebuilds the page on every run.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600;700;800&"
    "family=JetBrains+Mono:wght@400;500&"
    "family=Playfair+Display:ital,wght@1,400;1,700;1,900&display=swap"
)

# Spectrum colours cycled across the title-odds chips (never page backgrounds).
_CHIP_CLASSES = ("c-indigo", "c-teal", "c-amber", "c-rose")

_FOOTER_NOTE = (
    "Rebuilt automatically from state.json on every tracker run. "
    "FIFA World Cup 2026 Tracker."
)


def _pct(prob: float) -> str:
    """Format a 0-1 probability as a percentage string e.g. '18.0%'."""
    return f"{prob * 100:.1f}%"


def _esc_body(text: str) -> str:
    """HTML-escape a plain-text message body and convert newlines to <br>."""
    return escape(text).replace("\n", "<br>")


def _render_title_odds(bracket: dict) -> str:
    """Top ~10 teams by title probability as solid spectrum chips."""
    title_odds = bracket.get("title_odds") or {}
    if not title_odds:
        return ""

    top = sorted(title_odds.items(), key=lambda kv: kv[1], reverse=True)[:10]
    chips = []
    for i, (team, prob) in enumerate(top):
        cls = _CHIP_CLASSES[i % len(_CHIP_CLASSES)]
        chips.append(
            f'      <span class="chip {cls}">'
            f'<span class="chip-team">{escape(str(team))}</span>'
            f'<span class="chip-pct">{_pct(prob)}</span></span>'
        )

    return (
        '    <h2 class="section-label">Title odds — top contenders</h2>\n'
        '    <div class="chips">\n'
        + "\n".join(chips)
        + "\n    </div>\n"
    )


def _render_days(days: list[dict]) -> str:
    """Reverse-chronological (newest first) list of day cards."""
    if not days:
        return '    <p class="empty">No matchdays recorded yet.</p>\n'

    ordered = sorted(days, key=lambda d: d.get("date", ""), reverse=True)
    cards = []
    for day in ordered:
        date = escape(str(day.get("date", "")))
        messages = day.get("messages") or []
        msg_html = "".join(
            f'      <div class="day-msg">{_esc_body(str(m.get("body", "")))}</div>\n'
            for m in messages
            if m.get("sent", True)
        )
        if not msg_html:
            msg_html = '      <div class="day-msg empty">No messages.</div>\n'
        cards.append(
            f'    <article class="day-card">\n'
            f'      <h3 class="day-date">{date}</h3>\n'
            f"{msg_html}"
            f"    </article>\n"
        )
    return "".join(cards)


def render(state: dict, path) -> None:
    """Render the full standalone archive page to `path`."""
    days = state.get("days") or []
    bracket = state.get("bracket") or {}

    odds_section = _render_title_odds(bracket)
    days_section = _render_days(days)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>World Cup 2026 Tracker</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="{GOOGLE_FONTS}">
  <link rel="stylesheet" href="style.css">
  <style>
    /* Brand tokens inline so the page renders on-brand even if style.css
       fails to load. Page background is always warm cream. */
    :root {{
      --bg: #F5F1EB; --bg-card: #FFFFFF; --crimson: #E0001C;
      --indigo: #1E40AF; --teal: #0F766E; --amber: #B45309; --rose: #BE185D;
      --text: #0F0F0F; --text-muted: rgba(15,15,15,0.65);
      --text-faint: rgba(15,15,15,0.40);
      --shadow: 4px 4px 0 0 var(--text);
      --shadow-crimson: 4px 4px 0 0 var(--crimson);
      --font-hero: 'Playfair Display', serif;
      --font-body: 'Inter', sans-serif;
      --font-label: 'JetBrains Mono', monospace;
    }}
    body {{ background: #F5F1EB; }}
  </style>
</head>
<body>
  <main class="container">
    <header class="hero">
      <p class="eyebrow">FIFA World Cup 2026 — Live Tracker</p>
      <h1 class="hero-title">World <em>Cup</em> 2026 Tracker</h1>
      <p class="hero-desc">Daily predictions, results, and title odds — machine-modelled, rebuilt every matchday.</p>
    </header>

{odds_section}
    <h2 class="section-label">Matchday log</h2>
{days_section}
    <footer class="footer">{escape(_FOOTER_NOTE)}</footer>
  </main>
</body>
</html>
"""

    Path(path).write_text(html, encoding="utf-8")
