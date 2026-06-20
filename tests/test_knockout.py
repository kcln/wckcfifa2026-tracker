from src import knockout as k


def test_abbr_known_and_fallback():
    assert k.abbr("South Korea") == "KOR"
    assert k.abbr("Côte") == "CT"[:3] or k.abbr("Curaçao") == "CUW"
    assert k.abbr("Spain") == "ESP"
    # unknown -> alpha-only first 3 upper
    assert k.abbr("Narnia") == "NAR"


def _grp(*teams, played):
    return [{"team": t, "played": played} for t in teams]


GROUPS = {  # undecided (played 1): group slots project the whole group
    "A": _grp("Mexico", "South Korea", "Czechia", "South Africa", played=1),
    "E": _grp("Germany", "Ivory Coast", "Ecuador", "Curaçao", played=1),
}
GROUPS_DONE = {  # decided (played 3): group slots collapse to the qualifier
    "A": _grp("Mexico", "South Korea", "Czechia", "South Africa", played=3),
}


def test_group_slot_projects_whole_group_in_order_while_undecided():
    # the circled-box case: 1E -> all of group E in standings order
    assert k.slot_label("1E", GROUPS) == "GER / CIV / ECU / CUW"
    # both winner and runner-up slots show the full group
    assert k.slot_label("2A", GROUPS) == "MEX / KOR / CZE / RSA"
    assert k.slot_label("1A", GROUPS) == "MEX / KOR / CZE / RSA"


def test_group_slot_collapses_to_qualifier_when_decided():
    assert k.slot_label("1A", GROUPS_DONE) == "MEX"   # group A winner
    assert k.slot_label("2A", GROUPS_DONE) == "KOR"   # group A runner-up


def test_slot_label_best_third_stays_until_resolved():
    assert k.slot_label("3A/B/C/D/F", GROUPS) == "3A/B/C/D/F"


def test_slot_label_winner_feeder_resolves_when_known():
    assert k.slot_label("W73", GROUPS) == "W73"               # not decided
    assert k.slot_label("W73", GROUPS, winners={"73": "Spain"}) == "ESP"
    assert k.slot_label("L101", GROUPS, losers={"101": "Brazil"}) == "BRA"


def test_slot_label_unknown_group_returns_token():
    assert k.slot_label("2Z", GROUPS) == "2Z"


def test_slot_locked_only_when_group_complete():
    incomplete = {"A": [{"team": "Mexico", "played": 1},
                        {"team": "South Korea", "played": 1},
                        {"team": "Czechia", "played": 1},
                        {"team": "RSA", "played": 1}]}
    complete = {"A": [{"team": "Mexico", "played": 3},
                      {"team": "South Korea", "played": 3},
                      {"team": "Czechia", "played": 3},
                      {"team": "RSA", "played": 3}]}
    assert k.slot_locked("1A", incomplete) is False     # projected
    assert k.slot_locked("1A", complete) is True        # decided
    assert k.slot_locked("2A", complete) is True
    assert k.slot_locked("3A/B/C/D/F", complete) is False
    assert k.slot_locked("W73", complete) is False
    assert k.slot_locked("W73", complete, winners={"73": "Spain"}) is True


# --- clinched_qualifiers: FIFA/ESPN-style points-secure Round-of-32 berths ---

def _rows(*pairs):
    return [{"team": t, "played": p, "points": pt} for t, p, pt in pairs]


def _sched(*fixtures):
    """fixtures: (home, away) tuples -> a one-day schedule of unplayed group
    matches (no status/hg => treated as remaining)."""
    return [{"date": "2026-06-24",
             "matches": [{"stage": "group", "home": h, "away": a}
                         for h, a in fixtures]}]


def test_clinched_top2_basic_group_a():
    # Mexico 6, SK 3, CZE 1, RSA 1 (each played 2); remaining: CZEvMEX, SKvRSA.
    # Mexico's floor is 6; only SK can reach 6 -> at most one rival -> clinched.
    groups = {"A": _rows(("Mexico", 2, 6), ("South Korea", 2, 3),
                         ("Czech Republic", 2, 1), ("South Africa", 2, 1))}
    sched = _sched(("Czech Republic", "Mexico"), ("South Korea", "South Africa"))
    clinched = k.clinched_qualifiers(groups, sched)
    assert clinched.get("A") == {"Mexico"}
    assert k.clinched_set(groups, sched) == {"Mexico"}


def test_no_clinch_early_in_group():
    # Everyone has played one; two fixtures left each -> nothing is secure yet.
    groups = {"A": _rows(("Mexico", 1, 3), ("South Korea", 1, 3),
                         ("Czech Republic", 1, 0), ("South Africa", 1, 0))}
    sched = _sched(("Mexico", "Czech Republic"), ("South Korea", "South Africa"),
                   ("Mexico", "South Korea"), ("Czech Republic", "South Africa"))
    assert k.clinched_qualifiers(groups, sched) == {}


def test_clinch_requires_points_security_not_goal_difference():
    # A=6 but two rivals can still reach 6 (B beats D, C beats A), so A could be
    # squeezed to 3rd on the tie -> FIFA would NOT mark A qualified yet.
    groups = {"I": _rows(("Argentina", 2, 6), ("Norway", 2, 3),
                         ("France", 2, 3), ("Senegal", 2, 0))}
    sched = _sched(("Norway", "Senegal"), ("France", "Argentina"))
    assert "Argentina" not in k.clinched_set(groups, sched)
