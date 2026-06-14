"""
message_builder.py — plain-text message bodies for Telegram and the web archive.

Public API
----------
morning_brief(date_iso, matches) -> str
post_match(match) -> str
daily_recap(date_iso, matches, group_tables) -> str
bracket_update(title_odds, advancement) -> str
champion_recap(team) -> str
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

# Kickoff times are shown in this fixed four-zone order (KC's spec).
_KICKOFF_ZONES = (
    ("PT",  ZoneInfo("America/Los_Angeles")),
    ("CT",  ZoneInfo("America/Chicago")),
    ("ET",  ZoneInfo("America/New_York")),
    ("IST", ZoneInfo("Asia/Kolkata")),
)

# Host country per 2026 venue city (fixtures carry city-only venue strings).
_VENUE_COUNTRY = {
    "Atlanta": "USA",
    "Boston (Foxborough)": "USA",
    "Dallas (Arlington)": "USA",
    "Guadalajara (Zapopan)": "Mexico",
    "Houston": "USA",
    "Kansas City": "USA",
    "Los Angeles (Inglewood)": "USA",
    "Mexico City": "Mexico",
    "Miami (Miami Gardens)": "USA",
    "Monterrey (Guadalupe)": "Mexico",
    "New York/New Jersey (East Rutherford)": "USA",
    "Philadelphia": "USA",
    "San Francisco Bay Area (Santa Clara)": "USA",
    "Seattle": "USA",
    "Toronto": "Canada",
    "Vancouver": "Canada",
}


def place(venue: str) -> str:
    """'Mexico City, Mexico' from a venue city; city-only when unmapped,
    '' when missing."""
    if not venue:
        return ""
    country = _VENUE_COUNTRY.get(venue)
    return f"{venue}, {country}" if country else venue


def _place_of(match: dict) -> str:
    return place(match.get("venue") or "")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def kickoff_stack(kickoff_utc: str, match_date: str = "") -> str:
    """'12:00pm PT / 2:00pm CT / 3:00pm ET / 12:30am IST (+1d)' from an ISO
    UTC kickoff. Zones whose local date rolls past the match date get a
    (+1d) marker. Returns '' for missing/unparseable input."""
    if not kickoff_utc:
        return ""
    try:
        dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    except ValueError:
        return ""
    parts = []
    for label, tz in _KICKOFF_ZONES:
        local = dt.astimezone(tz)
        stamp = local.strftime("%-I:%M %p").lower().replace(" ", "")
        rolled = " (+1d)" if (match_date
                              and local.date().isoformat() > match_date) else ""
        parts.append(f"{stamp} {label}{rolled}")
    return " / ".join(parts)

def _argmax_outcome(prediction: dict) -> str:
    """Return 'home', 'draw', or 'away' — whichever probability is highest."""
    return max(("home", "draw", "away"), key=lambda k: prediction[k])


def _pct(prob: float) -> str:
    """Format a 0-1 probability as a percentage string e.g. '50.0%'."""
    return f"{prob * 100:.1f}%"


def _pick_label(match: dict) -> str:
    """
    Return the human-readable pick from a match's prediction:
    the home team name, away team name, or 'Draw'.
    """
    outcome = _argmax_outcome(match["prediction"])
    if outcome == "home":
        return match["home"]
    if outcome == "away":
        return match["away"]
    return "Draw"


def _event_lines(events, indent: str = "  ") -> list[str]:
    """Render goal and red-card events as indented timeline lines:

        ⚽ 21' Ismael Saibari (Morocco)
        ⚽ 64' Vinícius Jr (Brazil, pen)
        🟥 80' Casemiro (Brazil)

    Goals are listed first (feed order, i.e. chronological), then red cards.
    Own goals and penalties are annotated. Empty/missing events -> no lines."""
    if not events:
        return []
    goals = [e for e in events if e.get("kind") in ("goal", "own_goal", "penalty")]
    reds = [e for e in events if e.get("kind") == "red"]
    lines: list[str] = []
    for e in goals:
        annot = {"own_goal": ", OG", "penalty": ", pen"}.get(e.get("kind"), "")
        name = e.get("player") or "Unknown"
        minute = e.get("minute") or ""
        lines.append(f"{indent}⚽ {minute} {name} ({e.get('team', '')}{annot})")
    for e in reds:
        name = e.get("player") or "Unknown"
        minute = e.get("minute") or ""
        lines.append(f"{indent}🟥 {minute} {name} ({e.get('team', '')})")
    return lines


def _actual_outcome(result: dict) -> str:
    """Derive 'home', 'draw', or 'away' from a result dict."""
    hg = result["home_goals"]
    ag = result["away_goals"]
    if hg > ag:
        return "home"
    if ag > hg:
        return "away"
    return "draw"


def _post_match_line(match: dict) -> str:
    """
    Format a single post-match result line:
    'Home H-A Away   ✓' or '... ✗'
    Includes a Prediction label showing what was called.
    """
    home = match["home"]
    away = match["away"]
    result = match["result"]
    hg = result["home_goals"]
    ag = result["away_goals"]

    predicted = _argmax_outcome(match["prediction"])
    actual = _actual_outcome(result)
    tick = "✓" if predicted == actual else "✗"

    pred_label = _pick_label(match)
    line = f"{home} {hg}-{ag} {away}  {tick}  (Prediction: {pred_label})"
    loc = _place_of(match)
    return f"{line}  —  {loc}" if loc else line


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def morning_brief(date_iso: str, matches: list[dict]) -> str:
    """
    Daily pre-matchday brief.

    Header line with the date, followed by one line per match showing the
    teams, the Prediction (argmax pick as team name or 'Draw'), and the three
    probabilities as percentages.
    """
    lines: list[str] = [
        f"FIFA World Cup 2026 — Matchday Brief",
        f"Date: {date_iso}",
        "",
    ]
    for m in matches:
        pred = m["prediction"]
        pick = _pick_label(m)
        home_pct = _pct(pred["home"])
        draw_pct = _pct(pred["draw"])
        away_pct = _pct(pred["away"])
        ko = kickoff_stack(m.get("kickoff_utc", ""), m.get("date", ""))
        loc = _place_of(m)
        vs = f"{m['home']} vs {m['away']}"
        if loc:
            vs += f"  —  {loc}"
        if ko:
            lines.append(f"{vs}  —  Kickoff {ko}")
            lines.append(
                f"  Prediction: {pick}  |  "
                f"Home {home_pct}  Draw {draw_pct}  Away {away_pct}"
            )
        else:
            lines.append(
                f"{vs}  |  "
                f"Prediction: {pick}  |  "
                f"Home {home_pct}  Draw {draw_pct}  Away {away_pct}"
            )
    return "\n".join(lines)


def half_time(match: dict, home_goals: int, away_goals: int,
              events=None) -> str:
    """
    Half-time score update for a live match, with the pre-match pick for
    context (predictions are not re-run mid-match). First-half goal scorers
    and any red cards (player, country, minute) are listed when available.
    """
    pick = _pick_label(match)
    loc = _place_of(match)
    lines = [f"Half-time: {match['home']} {home_goals}-{away_goals} "
             f"{match['away']}"]
    if loc:
        lines.append(loc)
    lines.extend(_event_lines(events))
    lines.append(f"Prediction: {pick}")
    return "\n".join(lines)


def post_match(match: dict) -> str:
    """
    Single post-match result summary.

    Leads with a "Full time" label (soccer's final-whistle term, parallel to
    the "Half-time:" updates), then the scoreline and ✓/✗ for whether the
    pre-match argmax prediction matched the actual outcome, followed by goal
    scorers and red cards (player, country, minute) when the feed provides them.

    The label is its own line — kept off the score line so the archive's
    winner-bolding still targets the team names, not the label.
    """
    lines = ["Full time", _post_match_line(match)]
    lines.extend(_event_lines((match.get("result") or {}).get("events")))
    return "\n".join(lines)


def daily_recap(date_iso: str, matches: list[dict], group_tables: dict) -> str:
    """
    End-of-day recap: date header, each completed result, then group standings.

    `group_tables` maps group letter -> list of row dicts
    [{team, played, points, gd, gf, ga}] (already sorted by standings).
    """
    lines: list[str] = [
        f"FIFA World Cup 2026 — Daily Recap",
        f"Date: {date_iso}",
        "",
        "Results:",
    ]

    resolved = [m for m in matches if m.get("result")]
    pending = [m for m in matches if not m.get("result")]

    for m in resolved:
        lines.append("  " + _post_match_line(m))
        lines.extend(_event_lines((m.get("result") or {}).get("events"),
                                  indent="    "))

    # A match with no recorded result (e.g. a feed name we couldn't reconcile)
    # is listed explicitly rather than silently dropped from the day.
    if pending:
        lines.append("")
        lines.append("No result recorded:")
        for m in pending:
            lines.append(f"  {m['home']} vs {m['away']}")

    if group_tables:
        lines.append("")
        lines.append("Group Standings:")
        for group_letter, rows in sorted(group_tables.items()):
            lines.append(f"  Group {group_letter}")
            lines.append(f"  {'Team':<20} {'P':>2}  {'Pts':>3}  {'GD':>4}  {'GF':>3}  {'GA':>3}")
            for row in rows:
                lines.append(
                    f"  {row['team']:<20} {row['played']:>2}  "
                    f"{row['points']:>3}  {row['gd']:>+4}  "
                    f"{row['gf']:>3}  {row['ga']:>3}"
                )
            lines.append("")

    return "\n".join(lines).rstrip()


def bracket_update(title_odds: dict, advancement: dict) -> str:
    """
    Knockout bracket update showing top teams by title probability.

    Displays a header and the top 10 teams (by title_odds) formatted as
    'Team — NN.N%'. `advancement` (team -> prob) is available for optional
    round-of-16 / QF notes but is not required to be non-empty.
    """
    lines: list[str] = [
        "FIFA World Cup 2026 — Title Odds Update",
        "",
        "Top title probabilities:",
    ]

    top = sorted(title_odds.items(), key=lambda kv: kv[1], reverse=True)[:10]
    for rank, (team, prob) in enumerate(top, start=1):
        lines.append(f"  {rank:>2}. {team:<20} — {_pct(prob)}")

    if advancement:
        lines.append("")
        lines.append("Advancement odds (next round):")
        adv_top = sorted(advancement.items(), key=lambda kv: kv[1], reverse=True)[:10]
        for team, prob in adv_top:
            lines.append(f"  {team:<20} — {_pct(prob)}")

    return "\n".join(lines)


def champion_recap(team: str) -> str:
    """
    Celebratory closing message naming the World Cup champion.
    """
    return (
        f"FIFA World Cup 2026 — Final\n"
        f"\n"
        f"Champion: {team}\n"
        f"\n"
        f"Congratulations to {team}! World Cup 2026 is complete."
    )
