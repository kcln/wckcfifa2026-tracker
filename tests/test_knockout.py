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


# --- clinched_thirds: best-third (top 8 of 12) Round-of-32 berths ---

def _complete4(g, third_gd, third_pts=3):
    """A consistent complete (played-3) 4-team group: 9 > 6 > 3rd(3 pts) > 0.
    The 3rd row's GD is the knob used to rank thirds across groups."""
    return [
        {"team": f"{g}1", "played": 3, "points": 9, "gd": 9, "gf": 9, "ga": 0},
        {"team": f"{g}2", "played": 3, "points": 6, "gd": 3, "gf": 5, "ga": 2},
        {"team": f"{g}3", "played": 3, "points": third_pts,
         "gd": third_gd, "gf": 3, "ga": 3},
        {"team": f"{g}4", "played": 3, "points": 0, "gd": -9, "gf": 0, "ga": 9},
    ]


def test_clinched_thirds_top8_qualify_ninth_excluded():
    # 9 complete groups; thirds tie on points but have distinct GD (8..0). Only
    # the best 8 third-place teams advance, so the 9th (lowest GD) is NOT clinched.
    groups = {chr(ord("A") + i): _complete4(chr(ord("A") + i), 8 - i)
              for i in range(9)}
    clinched = k.clinched_thirds(groups, [])
    assert clinched == {f"{chr(ord('A') + i)}3" for i in range(8)}  # GD 8..1
    assert "I3" not in clinched                                     # GD 0 -> 9th


def test_clinched_thirds_incomplete_group_blocks_borderline_third():
    # 7 strong complete thirds (GD 5) rank above a borderline complete third
    # (GD 0). An unfinished group whose third can still reach 3 pts is the 8th
    # threat, so the borderline third is NOT yet clinched; the 7 strong ones are.
    groups = {chr(ord("A") + i): _complete4(chr(ord("A") + i), 5)
              for i in range(7)}
    groups["H"] = _complete4("H", 0)
    groups["H"][2]["team"] = "Borderline"
    groups["J"] = [                       # incomplete: 2 played, 2 fixtures left
        {"team": "J1", "played": 2, "points": 6, "gd": 4, "gf": 4, "ga": 0},
        {"team": "J2", "played": 2, "points": 3, "gd": 1, "gf": 2, "ga": 1},
        {"team": "J3", "played": 2, "points": 3, "gd": 0, "gf": 2, "ga": 2},
        {"team": "J4", "played": 2, "points": 0, "gd": -5, "gf": 0, "ga": 5},
    ]
    sched = _sched(("J1", "J4"), ("J2", "J3"))
    clinched = k.clinched_thirds(groups, sched)
    assert "Borderline" not in clinched
    assert all(f"{chr(ord('A') + i)}3" in clinched for i in range(7))


def test_clinched_all_unions_top2_and_thirds():
    groups = {chr(ord("A") + i): _complete4(chr(ord("A") + i), 8 - i)
              for i in range(9)}
    allc = k.clinched_all(groups, [])
    assert "A1" in allc and "A2" in allc        # group winner + runner-up (top 2)
    assert "A3" in allc                          # a qualifying third (best GD)
    assert "I3" not in allc                      # 9th-best third, not in
