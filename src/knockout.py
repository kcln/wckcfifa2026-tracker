"""Knockout-bracket slot resolution.

The seed encodes knockout fixtures with placeholder slots: group winners/
runners-up ("1A", "2C"), best-third combinations ("3A/B/C/D/F"), and feeders
referencing earlier matches ("W73" = winner of match 73, "L101" = loser).

`slot_label` turns a slot token into a 2-3 letter country code by reading the
live group standings (so it tracks the table day to day and locks to the real
qualifier once a group finishes). Tokens that aren't yet determinable
(best-third slots, unplayed feeders) are returned as-is until they resolve.
"""
from __future__ import annotations

import itertools

# 48-team FIFA-style 3-letter codes.
ABBR = {
    "Mexico": "MEX", "South Korea": "KOR", "Czech Republic": "CZE",
    "South Africa": "RSA", "Canada": "CAN", "Bosnia & Herzegovina": "BIH",
    "Qatar": "QAT", "Switzerland": "SUI", "Scotland": "SCO", "Brazil": "BRA",
    "Morocco": "MAR", "Haiti": "HAI", "USA": "USA", "Australia": "AUS",
    "Turkey": "TUR", "Paraguay": "PAR", "Germany": "GER", "Ivory Coast": "CIV",
    "Ecuador": "ECU", "Curaçao": "CUW", "Sweden": "SWE", "Japan": "JPN",
    "Netherlands": "NED", "Tunisia": "TUN", "Iran": "IRN", "New Zealand": "NZL",
    "Belgium": "BEL", "Egypt": "EGY", "Saudi Arabia": "KSA", "Uruguay": "URU",
    "Cape Verde": "CPV", "Spain": "ESP", "France": "FRA", "Iraq": "IRQ",
    "Norway": "NOR", "Senegal": "SEN", "Algeria": "ALG", "Argentina": "ARG",
    "Austria": "AUT", "Jordan": "JOR", "Colombia": "COL", "DR Congo": "COD",
    "Portugal": "POR", "Uzbekistan": "UZB", "Croatia": "CRO", "England": "ENG",
    "Ghana": "GHA", "Panama": "PAN",
}


def abbr(team: str) -> str:
    """3-letter code for a country (best-effort fallback for unknown names)."""
    if not team:
        return ""
    return ABBR.get(team, "".join(c for c in team if c.isalpha())[:3].upper())


def group_order(grp: str, groups: dict) -> str:
    """All of a group's teams as codes in current standings order, e.g.
    'GER / CIV / ECU / CUW' — the projected contenders for that slot."""
    rows = groups.get(grp) or []
    return " / ".join(abbr(r["team"]) for r in rows if r.get("team"))


def _remaining_group_fixtures(groups: dict, schedule: list) -> dict:
    """Per group letter, the (home, away) of every group match not yet played.
    A match counts as played once it has a full-time score recorded."""
    team2grp = {t["team"]: g for g, rows in (groups or {}).items()
                for t in rows if t.get("team")}
    rem: dict = {g: [] for g in (groups or {})}
    for day in schedule or []:
        for m in day.get("matches", []):
            if m.get("stage") != "group":
                continue
            if m.get("status") == "FT" and m.get("hg") is not None:
                continue                                   # already played
            grp = team2grp.get(m.get("home"))
            if grp is not None:
                rem[grp].append((m.get("home"), m.get("away")))
    return rem


def clinched_qualifiers(groups: dict, schedule: list) -> dict:
    """Group letter -> set of teams that have mathematically secured a top-2
    (Round-of-32) finish, the way FIFA/ESPN mark qualification: POINTS-secure
    only. Goal difference is treated as reversible (future margins are
    unbounded), so a GD-only lead never counts as clinched.

    A team is clinched iff in EVERY completion of its group's remaining
    fixtures, at most one rival finishes on greater-or-equal points (a tie
    counts as a threat, since GD or the drawing of lots could drop the team to
    3rd). Best-third qualification is cross-group and out of scope here."""
    rem = _remaining_group_fixtures(groups, schedule)
    out: dict = {}
    for grp, rows in (groups or {}).items():
        base = {t["team"]: t.get("points", 0) for t in rows if t.get("team")}
        teams = list(base)
        fixtures = [(h, a) for h, a in rem.get(grp, [])
                    if h in base and a in base]
        # Only trust a clinch when played + known-remaining games account for the
        # full round-robin; otherwise the schedule is incomplete and an empty
        # remaining list would falsely read as "group over".
        n = len(teams)
        expected = n * (n - 1) // 2
        games_played = sum(t.get("played", 0) for t in rows) // 2
        if games_played + len(fixtures) != expected:
            continue
        safe = set(teams)
        for combo in itertools.product((0, 1, 2), repeat=len(fixtures)):
            pts = dict(base)
            for (h, a), o in zip(fixtures, combo):
                if o == 0:
                    pts[h] += 3
                elif o == 1:
                    pts[h] += 1
                    pts[a] += 1
                else:
                    pts[a] += 3
            for t in list(safe):
                if sum(1 for j in teams if j != t and pts[j] >= pts[t]) > 1:
                    safe.discard(t)
            if not safe:
                break
        if safe:
            out[grp] = safe
    return out


def clinched_set(groups: dict, schedule: list) -> set:
    """Flat set of all teams that have clinched a Round-of-32 berth."""
    return {t for teams in clinched_qualifiers(groups, schedule).values()
            for t in teams}


def _group_complete(grp: str, groups: dict) -> bool:
    """A group is decided once every team has played all its group games (a
    4-team round-robin = 3 each), so 1st/2nd are final."""
    rows = groups.get(grp) or []
    if not rows:
        return False
    games = len(rows) - 1
    return all(r.get("played", 0) >= games for r in rows)


def slot_locked(token: str, groups: dict, winners: dict | None = None,
                losers: dict | None = None) -> bool:
    """True when a slot's team is FINAL (not a live projection): a group
    winner/runner-up whose group has finished, or a feeder that's been decided.
    Best-third slots and unplayed feeders are never locked here."""
    t = (token or "").strip()
    if len(t) >= 2 and t[0] in "12" and t[1:].isalpha() and "/" not in t:
        return _group_complete(t[1:], groups)
    if t[:1] in ("W", "L") and t[1:].isdigit():
        table = (winners if t[0] == "W" else losers) or {}
        return t[1:] in table
    return False


def slot_label(token: str, groups: dict, winners: dict | None = None,
               losers: dict | None = None) -> str:
    """Best available label for a knockout slot token.

    Group slots ('1A'/'2C') show the WHOLE group as codes in current standings
    order ('GER / CIV / ECU / CUW') while the group is undecided, and collapse
    to the single qualifier once it finishes. 'W73'/'L101' -> the winner/loser
    code once that match is decided; best-third ('3A/B/.../F') and undecided
    feeders are returned unchanged.
    """
    t = (token or "").strip()
    if (len(t) >= 2 and t[0] in "12" and t[1:].isalpha() and "/" not in t):
        grp = t[1:]
        rows = groups.get(grp) or []
        if not rows:
            return t
        if _group_complete(grp, groups):              # decided -> the qualifier
            pos = int(t[0]) - 1
            return abbr(rows[pos]["team"]) if len(rows) > pos else t
        return group_order(grp, groups)               # projected -> whole group
    if t[:1] in ("W", "L") and t[1:].isdigit():
        table = (winners if t[0] == "W" else losers) or {}
        return abbr(table[t[1:]]) if t[1:] in table else t
    return t                              # best-third / unknown -> as-is
