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
        if not fixtures:
            # Group is finished: the actual top two (final standings, GD/GF
            # already applied) are through — never re-derive from points alone,
            # which would wrongly drop a runner-up that's level on points with
            # the 3rd-placed team but ahead on goal difference.
            if len(rows) >= 2:
                out[grp] = {rows[0]["team"], rows[1]["team"]}
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
    """Flat set of all teams that have clinched a top-2 Round-of-32 berth."""
    return {t for teams in clinched_qualifiers(groups, schedule).values()
            for t in teams}


def _max_third_points(rows: list, fixtures: list) -> int:
    """Highest points total any 3rd-place finisher of this group could end on,
    across every completion of its remaining fixtures (points only)."""
    base = {r["team"]: r.get("points", 0) for r in rows if r.get("team")}
    teams = list(base)
    best = 0
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
        order = sorted(teams, key=lambda t: pts[t], reverse=True)
        if len(order) >= 3:
            best = max(best, pts[order[2]])
    return best


def clinched_thirds(groups: dict, schedule: list) -> set:
    """Third-place teams that have mathematically secured one of the 8 best-third
    Round-of-32 berths. A complete group's 3rd-place team T is clinched iff at
    most 7 other groups can produce a third that ranks at-or-above T — so T is
    no worse than the 8th-best third. Other complete thirds are compared exactly
    (points, GD, GF; ties count against T); a still-incomplete group threatens T
    if its 3rd-place team could reach T's points in some completion (GD treated
    as reversible, matching FIFA's points-first clinching)."""
    rem = _remaining_group_fixtures(groups, schedule)
    complete: dict = {}                       # group -> (team, pts, gd, gf)
    incomplete_max: dict = {}                 # group -> max possible 3rd points
    for grp, rows in (groups or {}).items():
        base_teams = [r for r in rows if r.get("team")]
        n = len(base_teams)
        expected = n * (n - 1) // 2
        fixtures = [(h, a) for h, a in rem.get(grp, [])
                    if any(r["team"] == h for r in base_teams)
                    and any(r["team"] == a for r in base_teams)]
        played = sum(r.get("played", 0) for r in base_teams) // 2
        if played + len(fixtures) != expected:
            continue                          # inconsistent schedule -> skip
        if not fixtures and n >= 3:
            t = rows[2]
            complete[grp] = (t["team"], t.get("points", 0),
                             t.get("gd", 0), t.get("gf", 0))
        elif fixtures:
            incomplete_max[grp] = _max_third_points(base_teams, fixtures)

    clinched = set()
    for grp, (team, pts, gd, gf) in complete.items():
        threats = 0
        for g2, (_t, p2, d2, f2) in complete.items():
            if g2 != grp and (p2, d2, f2) >= (pts, gd, gf):
                threats += 1
        for mx in incomplete_max.values():
            if mx >= pts:
                threats += 1
        if threats <= 7:                      # T is no worse than 8th best third
            clinched.add(team)
    return clinched


def clinched_all(groups: dict, schedule: list) -> set:
    """Every team that has clinched a Round-of-32 berth — group top-2 AND the
    best-third qualifiers."""
    return clinched_set(groups, schedule) | clinched_thirds(groups, schedule)


def is_descriptor(s: str) -> bool:
    """True if `s` is still an unresolved knockout slot token ('1A', '2C',
    '3A/B/C/D/F', 'W74', 'L101') rather than a real team name."""
    s = (s or "").strip()
    if len(s) >= 2 and s[0] in "12" and s[1:].isalpha() and "/" not in s:
        return True
    if s[:1] == "3" and "/" in s:
        return True
    if s[:1] in ("W", "L") and s[1:].isdigit():
        return True
    return False


# FIFA Annex C round-of-32 third-place combination table. Keyed by the frozenset
# of the eight groups whose third-placed team qualified; the value maps each
# group WINNER (that faces a third) to the GROUP whose third it plays. There are
# 495 possible combinations; only realized ones are encoded as the tournament
# reaches them. {B,D,E,F,I,J,K,L} is the 2026 actual combination (Wikipedia /
# Annex C row 67).
_THIRD_PLACE_TABLE = {
    frozenset("BDEFIJKL"): {"A": "E", "B": "J", "D": "B", "E": "D",
                            "G": "I", "I": "F", "K": "L", "L": "K"},
}


def resolve_bracket(matches: list, group_tables: dict,
                    ko_results: dict | None = None) -> dict:
    """Map each knockout match's slot descriptors to real team names where they
    are determinable, so the site, Telegram, and result reconciliation use real
    matchups instead of '2A vs 2B'.

    Returns {match_id: (home, away)} for every non-group match; each side is the
    resolved team name, or the original descriptor when still unknown. Group
    winners/runners-up resolve once that group is decided and W##/L## feeders
    resolve as knockout results land. Best-third slots ('3A/B/C/D/F') resolve via
    FIFA's fixed combination table once every group is decided (the eight
    qualifying thirds are matched to group winners per Annex C); combinations the
    table doesn't encode are left as the honest placeholder."""
    gt = group_tables or {}
    ko_results = ko_results or {}
    winners, runners = {}, {}
    all_decided = bool(gt)
    third_rows = []
    for g, rows in gt.items():
        decided = (rows and len(rows) >= 2
                   and all(r.get("played", 0) >= len(rows) - 1 for r in rows))
        if decided:
            winners[g] = rows[0]["team"]
            runners[g] = rows[1]["team"]
            if len(rows) >= 3:
                third_rows.append((g, rows[2]))
        else:
            all_decided = False

    ko = sorted([m for m in matches if m.get("stage") not in ("group", None)],
                key=lambda m: int(m["id"]))

    # Best-third slot -> real team, via the FIFA Annex C combination table.
    third_assign = {}                        # third descriptor -> team name
    if all_decided and len(third_rows) == len(gt) and len(gt) >= 12:
        order = sorted(third_rows, key=lambda gr: (-gr[1].get("points", 0),
                                                   -gr[1].get("gd", 0),
                                                   -gr[1].get("gf", 0),
                                                   gr[1].get("team", "")))
        qual_groups = frozenset(g for g, _ in order[:8])
        winner_to_third = _THIRD_PLACE_TABLE.get(qual_groups)
        if winner_to_third:
            third_team = {g: r["team"] for g, r in third_rows}
            for m in ko:
                for side, other in (("home", "away"), ("away", "home")):
                    d = str(m.get(side, ""))
                    o = str(m.get(other, ""))
                    if (_is_third_desc(d) and len(o) >= 2 and o[0] == "1"
                            and o[1:] in winner_to_third):
                        tg = winner_to_third[o[1:]]    # which group's third
                        if tg in third_team:
                            third_assign[d] = third_team[tg]

    def resolve_one(desc, ko_w, ko_l):
        d = (desc or "").strip()
        if len(d) >= 2 and d[0] in "12" and d[1:].isalpha() and "/" not in d:
            return (winners if d[0] == "1" else runners).get(d[1:])
        if _is_third_desc(d):
            return third_assign.get(d)
        if d[:1] in ("W", "L") and d[1:].isdigit():
            return (ko_w if d[0] == "W" else ko_l).get(d[1:])
        return None

    ko_w, ko_l = {}, {}
    out = {}
    for m in ko:
        h = resolve_one(str(m.get("home", "")), ko_w, ko_l) or str(m.get("home", ""))
        a = resolve_one(str(m.get("away", "")), ko_w, ko_l) or str(m.get("away", ""))
        out[str(m["id"])] = (h, a)
        res = ko_results.get(str(m["id"])) or ko_results.get(m["id"])
        if res and not is_descriptor(h) and not is_descriptor(a):
            hg, ag = res.get("home_goals", 0), res.get("away_goals", 0)
            if hg != ag:                     # a knockout level at FT goes to
                ko_w[str(m["id"])] = h if hg > ag else a   # penalties — don't
                ko_l[str(m["id"])] = a if hg > ag else h   # guess the winner
    return out


def _is_third_desc(desc) -> bool:
    d = str(desc or "")
    return d[:1] == "3" and "/" in d


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
