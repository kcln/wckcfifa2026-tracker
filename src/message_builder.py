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
    return f"{home} {hg}-{ag} {away}  {tick}  (Prediction: {pred_label})"


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
        if ko:
            lines.append(f"{m['home']} vs {m['away']}  —  Kickoff {ko}")
            lines.append(
                f"  Prediction: {pick}  |  "
                f"Home {home_pct}  Draw {draw_pct}  Away {away_pct}"
            )
        else:
            lines.append(
                f"{m['home']} vs {m['away']}  |  "
                f"Prediction: {pick}  |  "
                f"Home {home_pct}  Draw {draw_pct}  Away {away_pct}"
            )
    return "\n".join(lines)


def half_time(match: dict, home_goals: int, away_goals: int) -> str:
    """
    Half-time score update for a live match, with the pre-match pick for
    context (predictions are not re-run mid-match).
    """
    pick = _pick_label(match)
    return (
        f"Half-time: {match['home']} {home_goals}-{away_goals} {match['away']}\n"
        f"Prediction: {pick}"
    )


def post_match(match: dict) -> str:
    """
    Single post-match result summary.

    Shows the scoreline and ✓/✗ for whether the pre-match argmax prediction
    matched the actual outcome (home win / draw / away win).
    """
    return _post_match_line(match)


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

    for m in matches:
        lines.append("  " + _post_match_line(m))

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
