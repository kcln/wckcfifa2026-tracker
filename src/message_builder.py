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


def _result_word(match: dict) -> str:
    """Human label for the actual outcome: 'Draw' or '<team> win'."""
    actual = _actual_outcome(match["result"])
    if actual == "draw":
        return "Draw"
    return f"{match['home']} win" if actual == "home" else f"{match['away']} win"


def fmt_accuracy(hits: int, total: int) -> str:
    """'x/y (n.n%)' — prediction accuracy. '0/0 (—)' when nothing's resolved."""
    if not total:
        return "0/0 (—)"
    return f"{hits}/{total} ({hits / total * 100:.1f}%)"


def _result_block(match: dict, *, indent: str = "", overall=None) -> list[str]:
    """A finished match as a multi-line block (KC's layout):

        Home H-A Away
        City, Country
          ⚽ scorers / 🟥 reds
        [Overall prediction: x/y (n%)]      (full-time message only)
        Prediction ✓: <pick>                (✓ if the model was right, else ✗)

    The city is always its own line and the prediction is always the last line.
    """
    r = match["result"]
    mark = "✓" if _argmax_outcome(match["prediction"]) == _actual_outcome(r) else "✗"
    home, away = match["home"], match["away"]
    hg, ag = r["home_goals"], r["away_goals"]
    # The winner (ESPN's recorded winner, incl. shootouts; else the higher score)
    # has their name bolded; a draw has none.
    win = r.get("winner") or (home if hg > ag else away if ag > hg else "")
    hn = f"<b>{home}</b>" if win == home else home
    an = f"<b>{away}</b>" if win == away else away
    shootout = r.get("home_pens") is not None and r.get("away_pens") is not None
    if shootout:                             # "1 (3) - 1 (4)", winner's pen bold
        hp, ap = r["home_pens"], r["away_pens"]
        hgs = f"{hg} (<b>{hp}</b>)" if win == home else f"{hg} ({hp})"
        ags = f"{ag} (<b>{ap}</b>)" if win == away else f"{ag} ({ap})"
        score = f"{hn} {hgs} - {ags} {an}"
    else:
        score = f"{hn} {hg} - {ag} {an}"
    lines = [f"{indent}{score}"]
    if shootout and win:                     # level in play -> name the pens winner
        lines.append(f"{indent}{win} win on penalties")
    loc = _place_of(match)
    if loc:
        lines.append(f"{indent}{loc}")
    lines.extend(_event_lines(r.get("events"), indent=indent + "  "))
    if overall is not None:
        lines.append(f"{indent}Overall prediction: {fmt_accuracy(*overall)}")
    lines.append(f"{indent}Prediction {mark}: {_pick_label(match)}")
    return lines


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def _pretty_date(date_iso: str) -> str:
    try:
        from datetime import datetime as _dt
        return _dt.strptime(date_iso, "%Y-%m-%d").strftime("%A, %B %-d")
    except ValueError:
        return date_iso


def _kickoff_key(m: dict):
    """Sort key putting matches in chronological kickoff order (id as tiebreak
    so matches without a kickoff stay stable)."""
    return (m.get("kickoff_utc") or "", str(m.get("id") or ""))


def _header(date_iso: str) -> list[str]:
    """Brand + date header used by every message — one item per line."""
    return ["🏆 FIFA World Cup 2026", _pretty_date(date_iso), ""]


def morning_brief(date_iso: str, matches: list[dict]) -> str:
    """
    Daily pre-matchday brief — one clean block per match.

    Win probabilities are labelled with the actual team names (not Home/Away,
    which read as confusing) and the model's pick is called out on its own line:

        Germany vs Curaçao
          Prediction: Germany
          Germany 77.8% · Draw 6.3% · Curaçao 15.9%
          🕐 10:00am PT / 12:00pm CT / 1:00pm ET / 10:30pm IST
          📍 Houston, USA
    """
    lines: list[str] = _header(date_iso) + ["Matchday Brief", ""]
    for m in sorted(matches, key=_kickoff_key):   # earliest kickoff first
        pred = m["prediction"]
        home, away = m["home"], m["away"]
        lines.append(f"{home} vs {away}")
        lines.append(f"  Prediction: {_pick_label(m)}")
        lines.append(
            f"  {home} {_pct(pred['home'])} · "
            f"Draw {_pct(pred['draw'])} · {away} {_pct(pred['away'])}")
        ko = kickoff_stack(m.get("kickoff_utc", ""), m.get("date", ""))
        if ko:
            lines.append(f"  🕐 {ko}")
        loc = _place_of(m)
        if loc:
            lines.append(f"  📍 {loc}")
        lines.append("")
    return "\n".join(lines).rstrip()


def half_time(match: dict, home_goals: int, away_goals: int,
              events=None) -> str:
    """
    Half-time score update for a live match, with the pre-match pick for
    context (predictions are not re-run mid-match). First-half goal scorers
    and any red cards (player, country, minute) are listed when available.
    """
    lines = _header(match.get("date", "")) + [
        "Half-time:",
        f"{match['home']} {home_goals} - {away_goals} {match['away']}"]
    loc = _place_of(match)
    if loc:
        lines.append(loc)
    lines.extend(_event_lines(events))
    lines.append(f"Prediction: {_pick_label(match)}")
    return "\n".join(lines)


def post_match(match: dict, overall=None) -> str:
    """
    Single post-match result summary:

        Full time
        Qatar 1-1 Switzerland  —  San Francisco Bay Area, USA
        Result: Draw  ·  Prediction: Switzerland  ✗ (0%)
        Overall prediction: 5/9 (55.6%)
        ⚽ 23' Scorer (Qatar)

    The score line is kept clean (no label) so the archive's winner-bolding
    still targets the team names. `overall` is an optional (hits, total) tally
    rendered as the running cumulative accuracy through this match — passed in
    by the tracker so it stays stable (independent of later matches).
    """
    lines = _header(match.get("date", "")) + ["Full time:"]
    lines += _result_block(match, overall=overall)
    return "\n".join(lines)


def daily_recap(date_iso: str, matches: list[dict], group_tables: dict,
                day_acc=None, overall_acc=None, qualified=None) -> str:
    """
    End-of-day recap: date header, each completed result, a prediction-accuracy
    line (today + cumulative), then group standings.

    `group_tables` maps group letter -> list of row dicts
    [{team, played, points, gd, gf, ga}] (already sorted by standings).
    `day_acc` / `overall_acc` are (hits, total) tallies from the tracker.
    `qualified` is a set of team names that have clinched a Round-of-32 berth;
    those rows get a leading `Q` marker (explained in the key).
    """
    qualified = qualified or set()
    lines: list[str] = _header(date_iso) + ["Daily Recap", "", "Results:"]

    matches = sorted(matches, key=_kickoff_key)   # chronological results
    resolved = [m for m in matches if m.get("result")]
    pending = [m for m in matches if not m.get("result")]

    # Each result is its own block, separated by a blank line for readability.
    blocks = ["\n".join(_result_block(m, indent="  ")) for m in resolved]
    if blocks:
        lines.append("\n\n".join(blocks))

    # A match with no recorded result (e.g. a feed name we couldn't reconcile)
    # is listed explicitly rather than silently dropped from the day.
    if pending:
        lines.append("")
        lines.append("No result recorded:")
        for m in pending:
            lines.append(f"  {m['home']} vs {m['away']}")

    # Prediction accuracy — today's and the running cumulative.
    if day_acc is not None or overall_acc is not None:
        lines.append("")
        parts = []
        if day_acc is not None:
            parts.append(f"today {fmt_accuracy(*day_acc)}")
        if overall_acc is not None:
            parts.append(f"overall {fmt_accuracy(*overall_acc)}")
        lines.append("Overall prediction — " + "  ·  ".join(parts))

    # Group-standings tables were dropped from the recap once the group stage
    # ended (they're frozen now); the website keeps the full tables. The
    # `group_tables`/`qualified` args are retained for signature compatibility.
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
