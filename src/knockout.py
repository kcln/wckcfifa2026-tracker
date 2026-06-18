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


def _group_pos(token: str, groups: dict) -> str | None:
    """Resolve a '1A'/'2C' slot to the country currently in that position."""
    pos = int(token[0]) - 1               # '1' -> 0 (winner), '2' -> 1 (r-up)
    rows = groups.get(token[1:]) or []
    if len(rows) > pos and rows[pos].get("team"):
        return abbr(rows[pos]["team"])
    return None


def slot_label(token: str, groups: dict, winners: dict | None = None,
               losers: dict | None = None) -> str:
    """Best available label for a knockout slot token.

    '1A'/'2C' -> country code from live standings; 'W73'/'L101' -> the
    winner/loser code once that match is decided; best-third ('3A/B/.../F') and
    still-undecided feeders are returned unchanged until they resolve.
    """
    t = (token or "").strip()
    if (len(t) >= 2 and t[0] in "12" and t[1:].isalpha() and "/" not in t):
        return _group_pos(t, groups) or t
    if t[:1] in ("W", "L") and t[1:].isdigit():
        table = (winners if t[0] == "W" else losers) or {}
        return abbr(table[t[1:]]) if t[1:] in table else t
    return t                              # best-third / unknown -> as-is
