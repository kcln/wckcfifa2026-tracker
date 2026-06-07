"""Bracket simulation: group tables, best-third tiebreak, knockout seeding,
and a Monte Carlo title/advancement simulator for the 2026 World Cup.

Data contract: a `tournament` dict shaped exactly like data/fixtures.json:
    {"groups": {"A": [team, ...], ...}, "matches": [match, ...]}
Group matches have stage=="group" and a `group` key. Completed matches have a
non-null `result` {"home_goals", "away_goals"} and are LOCKED (never re-simulated).
Unplayed matches (result is None) are simulated from the injected `match_prob`.

Knockout descriptors (home/away strings on stage != "group" matches):
    "1A" / "2A"       -> winner / runner-up of group A
    "3A/B/C/D/F"      -> a third-placed team drawn from one of the listed groups
    "W74" / "L101"    -> winner / loser of the match whose id is 74 / 101

THIRD-PLACE SIMPLIFICATION (known v1 limitation):
    FIFA assigns the 8 best third-placed teams to specific R32 berths via a fixed
    combination table keyed on *which* groups produced the qualifying thirds. We do
    NOT implement that table. Instead we collect every R32 slot whose descriptor is
    a third-place pattern, sort those slots by match id (a stable, deterministic
    order), and assign the 8 qualifying thirds to them in best-to-worst rank order.
    This produces a valid, reproducible bracket and gets the group winners and
    runners-up (the high-signal seeds) exactly right; only the precise opponent that
    each third-placed team faces may differ from the official draw.

Scoreline rule for SIMULATED group games (deterministic-from-rng):
    Given a sampled outcome we synthesize a small plausible scoreline so goal
    difference / goals-for tiebreaks have something to chew on:
        draw      -> 1-1
        home win  -> rng-pick of (1-0, 2-1, 2-0, 3-1)  [home larger]
        away win  -> mirror of the above (away larger)
    Locked games use their real recorded scoreline.
"""

from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# Group tables
# ---------------------------------------------------------------------------

def group_table(teams: list, matches: list) -> list:
    """Return rows [{team, played, points, gd, gf, ga}, ...] sorted by FIFA order:
    points desc, goal difference desc, goals-for desc, then team name (stable proxy
    for head-to-head). Only matches with a non-null `result` count."""
    stats = {t: {"team": t, "played": 0, "points": 0, "gd": 0, "gf": 0, "ga": 0}
             for t in teams}
    for m in matches:
        res = m.get("result")
        if not res:
            continue
        h, a = m["home"], m["away"]
        if h not in stats or a not in stats:
            continue
        hg, ag = res["home_goals"], res["away_goals"]
        sh, sa = stats[h], stats[a]
        sh["played"] += 1
        sa["played"] += 1
        sh["gf"] += hg
        sh["ga"] += ag
        sa["gf"] += ag
        sa["ga"] += hg
        sh["gd"] = sh["gf"] - sh["ga"]
        sa["gd"] = sa["gf"] - sa["ga"]
        if hg > ag:
            sh["points"] += 3
        elif ag > hg:
            sa["points"] += 3
        else:
            sh["points"] += 1
            sa["points"] += 1
    rows = list(stats.values())
    rows.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    return rows


def best_thirds(third_rows: list, n: int = 8) -> list:
    """Return names of the best n third-placed teams, sorted by points desc,
    gd desc, gf desc, team name."""
    rows = sorted(third_rows,
                  key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["team"]))
    return [r["team"] for r in rows[:n]]


# ---------------------------------------------------------------------------
# Precompute (done once per tournament, reused across iterations)
# ---------------------------------------------------------------------------

def _precompute(tournament: dict) -> dict:
    """Split matches into group / knockout structures and index by id."""
    groups = tournament["groups"]
    group_matches = {g: [] for g in groups}
    ko_matches = []
    for m in tournament["matches"]:
        if m["stage"] == "group":
            group_matches[m["group"]].append(m)
        else:
            ko_matches.append(m)
    # knockout matches played in id order so W##/L## look-ups resolve
    ko_matches.sort(key=lambda m: int(m["id"]))
    third_slots = sorted(
        [(m["id"], "home") for m in ko_matches if _is_third(m["home"])]
        + [(m["id"], "away") for m in ko_matches if _is_third(m["away"])],
        key=lambda s: (int(s[0]), s[1]),
    )
    return {
        "groups": groups,
        "group_matches": group_matches,
        "ko_matches": ko_matches,
        "third_slots": third_slots,
    }


def _is_third(descriptor: str) -> bool:
    return descriptor.startswith("3") and "/" in descriptor


# ---------------------------------------------------------------------------
# Scoreline synthesis
# ---------------------------------------------------------------------------

_HOME_WIN_LINES = ((1, 0), (2, 1), (2, 0), (3, 1))


def _sample_scoreline(outcome: str, rng) -> tuple:
    """Synthesize a small plausible (home_goals, away_goals) for a simulated game."""
    if outcome == "draw":
        return (1, 1)
    big, small = _HOME_WIN_LINES[rng.integers(len(_HOME_WIN_LINES))]
    if outcome == "home":
        return (big, small)
    return (small, big)  # away win


# ---------------------------------------------------------------------------
# Single simulation
# ---------------------------------------------------------------------------

def _sample_group_result(m: dict, match_prob, rng) -> dict:
    """Return a result dict for a group match, locking real results."""
    res = m.get("result")
    if res:
        return res
    p = match_prob(m["home"], m["away"])
    r = rng.random()
    if r < p["home"]:
        outcome = "home"
    elif r < p["home"] + p["draw"]:
        outcome = "draw"
    else:
        outcome = "away"
    hg, ag = _sample_scoreline(outcome, rng)
    return {"home_goals": hg, "away_goals": ag}


def _sample_ko_winner(home: str, away: str, m: dict, match_prob, rng) -> str:
    """Return the winning team of a knockout match. Locks real results; otherwise
    folds the draw probability evenly into the two sides and samples one winner."""
    res = m.get("result")
    if res:
        hg, ag = res["home_goals"], res["away_goals"]
        return home if hg >= ag else away
    p = match_prob(home, away)
    p_home = p["home"] + p["draw"] / 2.0
    p_away = p["away"] + p["draw"] / 2.0
    total = p_home + p_away
    return home if rng.random() < (p_home / total) else away


def _resolve_descriptor(desc: str, winners: dict, runners: dict,
                        third_assign: dict, ko_winner: dict, ko_loser: dict) -> str:
    """Resolve a single descriptor string to a concrete team name."""
    c = desc[0]
    if c == "1":
        return winners[desc[1]]
    if c == "2":
        return runners[desc[1]]
    if c == "3":
        return third_assign[desc]
    if c == "W":
        return ko_winner[desc[1:]]
    if c == "L":
        return ko_loser[desc[1:]]
    raise ValueError(f"unknown descriptor: {desc}")


def _simulate_groups(pre: dict, match_prob, rng):
    """Simulate all group games once; return (winners, runners, qualifying thirds)."""
    winners, runners = {}, {}
    third_rows = []
    for g, teams in pre["groups"].items():
        results = [
            {"home": m["home"], "away": m["away"],
             "result": _sample_group_result(m, match_prob, rng)}
            for m in pre["group_matches"][g]
        ]
        table = group_table(teams, results)
        winners[g] = table[0]["team"]
        runners[g] = table[1]["team"]
        third_rows.append({
            "team": table[2]["team"],
            "points": table[2]["points"],
            "gd": table[2]["gd"],
            "gf": table[2]["gf"],
        })
    qualifying = best_thirds(third_rows, n=8)
    return winners, runners, qualifying


def simulate_once(tournament: dict, match_prob, rng, _pre: dict = None) -> str:
    """Play all unplayed matches once, resolve the bracket, return champion name."""
    pre = _pre if _pre is not None else _precompute(tournament)

    winners, runners, qualifying = _simulate_groups(pre, match_prob, rng)

    # assign the 8 qualifying thirds to third-place R32 slots (see docstring).
    third_assign = {}
    for (mid, side), team in zip(pre["third_slots"], qualifying):
        m = next(x for x in pre["ko_matches"] if x["id"] == mid)
        third_assign[m[side]] = team

    ko_winner, ko_loser = {}, {}
    champion = None
    for m in pre["ko_matches"]:
        home = _resolve_descriptor(m["home"], winners, runners, third_assign,
                                   ko_winner, ko_loser)
        away = _resolve_descriptor(m["away"], winners, runners, third_assign,
                                   ko_winner, ko_loser)
        win = _sample_ko_winner(home, away, m, match_prob, rng)
        lose = away if win == home else home
        ko_winner[m["id"]] = win
        ko_loser[m["id"]] = lose
        if m["stage"] == "final":
            champion = win
    return champion


# ---------------------------------------------------------------------------
# Monte Carlo aggregates
# ---------------------------------------------------------------------------

def title_odds(tournament: dict, match_prob, iters: int = 10000) -> dict:
    """Run simulate_once `iters` times; return {team: probability} summing to 1.0."""
    pre = _precompute(tournament)
    parent = np.random.default_rng(0)
    counts = {}
    for _ in range(iters):
        rng = np.random.default_rng(parent.integers(2**63))
        champ = simulate_once(tournament, match_prob, rng, _pre=pre)
        counts[champ] = counts.get(champ, 0) + 1
    return {team: c / iters for team, c in counts.items()}


def advancement_odds(tournament: dict, match_prob, iters: int = 10000) -> dict:
    """Return {team: P(reaching the knockout stage / R32)}."""
    pre = _precompute(tournament)
    parent = np.random.default_rng(0)
    counts = {}
    for _ in range(iters):
        rng = np.random.default_rng(parent.integers(2**63))
        winners, runners, qualifying = _simulate_groups(pre, match_prob, rng)
        advancing = set(winners.values()) | set(runners.values()) | set(qualifying)
        for team in advancing:
            counts[team] = counts.get(team, 0) + 1
    return {team: c / iters for team, c in counts.items()}
