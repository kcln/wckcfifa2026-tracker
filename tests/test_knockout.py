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
