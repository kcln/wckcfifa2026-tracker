from src import knockout as k


def test_abbr_known_and_fallback():
    assert k.abbr("South Korea") == "KOR"
    assert k.abbr("Côte") == "CT"[:3] or k.abbr("Curaçao") == "CUW"
    assert k.abbr("Spain") == "ESP"
    # unknown -> alpha-only first 3 upper
    assert k.abbr("Narnia") == "NAR"


GROUPS = {
    "A": [{"team": "Mexico"}, {"team": "South Korea"}, {"team": "Czechia"}],
    "E": [{"team": "Germany"}, {"team": "Ecuador"}],
}


def test_slot_label_group_winner_and_runner_up():
    assert k.slot_label("1A", GROUPS) == "MEX"   # group A winner
    assert k.slot_label("2A", GROUPS) == "KOR"   # group A runner-up
    assert k.slot_label("1E", GROUPS) == "GER"


def test_slot_label_best_third_stays_until_resolved():
    assert k.slot_label("3A/B/C/D/F", GROUPS) == "3A/B/C/D/F"


def test_slot_label_winner_feeder_resolves_when_known():
    assert k.slot_label("W73", GROUPS) == "W73"               # not decided
    assert k.slot_label("W73", GROUPS, winners={"73": "Spain"}) == "ESP"
    assert k.slot_label("L101", GROUPS, losers={"101": "Brazil"}) == "BRA"


def test_slot_label_unknown_group_returns_token():
    assert k.slot_label("2Z", GROUPS) == "2Z"
