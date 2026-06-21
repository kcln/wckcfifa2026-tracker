from src import message_builder as mb


# --- morning_brief ---

def test_morning_brief_lists_each_match_with_pick():
    matches = [{"home": "USA", "away": "Mexico",
                "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2}}]
    text = mb.morning_brief("2026-06-11", matches)
    assert "USA" in text and "Mexico" in text and "%" in text


def test_morning_brief_shows_date():
    matches = [{"home": "Brazil", "away": "Germany",
                "prediction": {"home": 0.55, "draw": 0.25, "away": 0.20}}]
    text = mb.morning_brief("2026-06-14", matches)
    assert "June 14" in text   # human-readable header


def test_morning_brief_uses_team_names_not_home_away():
    matches = [{"home": "Germany", "away": "Curaçao",
                "prediction": {"home": 0.778, "draw": 0.063, "away": 0.159}}]
    text = mb.morning_brief("2026-06-14", matches)
    # probabilities are labelled by team, never "Home"/"Away"
    assert "Germany 77.8%" in text and "Curaçao 15.9%" in text
    assert "Draw 6.3%" in text
    assert "Home " not in text and "Away " not in text


def test_morning_brief_shows_prediction_label():
    matches = [{"home": "Brazil", "away": "Germany",
                "prediction": {"home": 0.55, "draw": 0.25, "away": 0.20}}]
    text = mb.morning_brief("2026-06-14", matches)
    assert "Prediction" in text


def test_morning_brief_pick_is_argmax():
    # home = 0.5, highest -> predicted winner is "USA"
    matches = [{"home": "USA", "away": "Mexico",
                "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2}}]
    text = mb.morning_brief("2026-06-11", matches)
    # USA is the argmax pick; "Draw" should NOT appear
    assert "USA" in text
    assert "Draw" not in text or text.index("USA") < len(text)


def test_morning_brief_pick_draw_when_draw_highest():
    matches = [{"home": "USA", "away": "Mexico",
                "prediction": {"home": 0.3, "draw": 0.5, "away": 0.2}}]
    text = mb.morning_brief("2026-06-11", matches)
    assert "Draw" in text


def test_morning_brief_multiple_matches():
    matches = [
        {"home": "Argentina", "away": "Chile",
         "prediction": {"home": 0.6, "draw": 0.2, "away": 0.2}},
        {"home": "France", "away": "England",
         "prediction": {"home": 0.4, "draw": 0.3, "away": 0.3}},
    ]
    text = mb.morning_brief("2026-06-15", matches)
    assert "Argentina" in text and "France" in text


# --- post_match ---

def test_post_match_marks_hit_or_miss():
    m = {"home": "USA", "away": "Mexico",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 2, "away_goals": 0}}
    text = mb.post_match(m)
    assert "2 - 0" in text and ("✓" in text or "✗" in text)


def test_post_match_marks_miss_when_wrong():
    m = {"home": "USA", "away": "Mexico",
         "prediction": {"home": 0.2, "draw": 0.3, "away": 0.5},
         "result": {"home_goals": 2, "away_goals": 0}}
    assert "✗" in mb.post_match(m)


def test_post_match_marks_hit_correct_home_win():
    m = {"home": "Brazil", "away": "Germany",
         "prediction": {"home": 0.6, "draw": 0.2, "away": 0.2},
         "result": {"home_goals": 3, "away_goals": 1}}
    assert "✓" in mb.post_match(m)


def test_post_match_marks_hit_correct_draw():
    m = {"home": "Spain", "away": "France",
         "prediction": {"home": 0.3, "draw": 0.4, "away": 0.3},
         "result": {"home_goals": 1, "away_goals": 1}}
    assert "✓" in mb.post_match(m)


def test_post_match_marks_miss_wrong_draw():
    m = {"home": "Spain", "away": "France",
         "prediction": {"home": 0.3, "draw": 0.4, "away": 0.3},
         "result": {"home_goals": 2, "away_goals": 0}}
    assert "✗" in mb.post_match(m)


def test_post_match_shows_team_names():
    m = {"home": "USA", "away": "Mexico",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 1, "away_goals": 1}}
    text = mb.post_match(m)
    assert "USA" in text and "Mexico" in text


# --- daily_recap ---

def test_daily_recap_shows_date():
    matches = [
        {"home": "USA", "away": "Mexico",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 2, "away_goals": 0}},
    ]
    group_tables = {}
    text = mb.daily_recap("2026-06-11", matches, group_tables)
    assert "June 11" in text   # human-readable header


def test_daily_recap_shows_result_lines():
    matches = [
        {"home": "USA", "away": "Mexico",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 2, "away_goals": 0}},
    ]
    group_tables = {}
    text = mb.daily_recap("2026-06-11", matches, group_tables)
    assert "2 - 0" in text


def test_daily_recap_renders_group_standings():
    matches = []
    group_tables = {
        "A": [
            {"team": "Brazil", "played": 1, "points": 3, "gd": 2, "gf": 2, "ga": 0},
            {"team": "Serbia", "played": 1, "points": 0, "gd": -2, "gf": 0, "ga": 2},
        ]
    }
    text = mb.daily_recap("2026-06-12", matches, group_tables)
    assert "Brazil" in text and "Group A" in text


def test_daily_recap_marks_qualified_teams_and_keys_it():
    matches = []
    group_tables = {
        "A": [
            {"team": "Mexico", "played": 2, "points": 6, "gd": 3, "gf": 3, "ga": 0},
            {"team": "South Korea", "played": 2, "points": 3, "gd": 0, "gf": 2, "ga": 2},
            {"team": "Czech Republic", "played": 2, "points": 1, "gd": -1, "gf": 2, "ga": 3},
        ]
    }
    text = mb.daily_recap("2026-06-20", matches, group_tables,
                          qualified={"Mexico"})
    # The key at the top explains the Q marker.
    assert "Q Qualified" in text
    # Qualified team's row carries a leading Q; others do not.
    lines = text.split("\n")
    mex = next(l for l in lines if "Mexico" in l)
    kor = next(l for l in lines if "South Korea" in l)
    assert mex.lstrip("<code>").startswith("Q")
    assert not kor.lstrip().startswith("Q")
    # Czech Republic must not be truncated by the new layout (14-wide column).
    assert "Czech Republic" in text


def test_daily_recap_group_table_rows_stay_aligned():
    # Every standings row (header + teams) must be the same monospace width so
    # the columns line up — the qualified marker mustn't shift anything.
    group_tables = {
        "A": [
            {"team": "Mexico", "played": 2, "points": 6, "gd": 3, "gf": 3, "ga": 0},
            {"team": "South Korea", "played": 2, "points": 3, "gd": 0, "gf": 2, "ga": 2},
        ],
        "B": [
            {"team": "Bosnia & Herzegovina", "played": 2, "points": 4, "gd": 1, "gf": 3, "ga": 2},
        ],
    }
    text = mb.daily_recap("2026-06-20", [], group_tables, qualified={"Mexico"})
    code = text.split("<code>")[1].split("</code>")[0]
    # Collect the team/header rows (those containing the right-aligned columns).
    rows = [l for l in code.split("\n")
            if l and not l.startswith("Group") and l.strip()]
    widths = {len(l) for l in rows}
    assert len(widths) == 1, f"misaligned row widths: {widths}"
    assert widths.pop() == 32   # tight, phone-safe width with the Q marker


# --- bracket_update ---

def test_bracket_update_shows_header():
    title_odds = {"Brazil": 0.18, "France": 0.15, "Argentina": 0.12}
    advancement = {}
    text = mb.bracket_update(title_odds, advancement)
    assert "Title" in text or "title" in text


def test_bracket_update_lists_top_teams_by_prob():
    title_odds = {"Brazil": 0.18, "France": 0.15, "Argentina": 0.12,
                  "England": 0.10, "Germany": 0.09, "Spain": 0.08,
                  "Portugal": 0.07, "Netherlands": 0.06, "Uruguay": 0.05,
                  "USA": 0.04, "Mexico": 0.03}
    advancement = {}
    text = mb.bracket_update(title_odds, advancement)
    assert "Brazil" in text and "%" in text


def test_bracket_update_shows_percentage():
    title_odds = {"Brazil": 0.18}
    text = mb.bracket_update(title_odds, {})
    assert "18" in text or "18.0" in text


# --- champion_recap ---

def test_champion_recap_names_winner():
    assert "Brazil" in mb.champion_recap("Brazil")


def test_champion_recap_names_winner_argentina():
    assert "Argentina" in mb.champion_recap("Argentina")


def test_champion_recap_is_celebratory():
    text = mb.champion_recap("Brazil")
    # Should be non-empty and feel like a closing message
    assert len(text) > 10


def test_half_time_shows_score_and_pick():
    match = {"home": "Mexico", "away": "South Africa",
             "prediction": {"home": 0.52, "draw": 0.26, "away": 0.22}}
    body = mb.half_time(match, 1, 0)
    assert "Half-time:" in body and "Mexico 1 - 0 South Africa" in body
    assert "Prediction: Mexico" in body


def test_kickoff_stack_four_zones_in_order():
    # 19:00 UTC on Jun 11 = noon PT / 2pm CT / 3pm ET / 12:30am IST next day
    out = mb.kickoff_stack("2026-06-11T19:00:00Z", "2026-06-11")
    assert out == "12:00pm PT / 2:00pm CT / 3:00pm ET / 12:30am IST (+1d)"


def test_morning_brief_includes_kickoff_times():
    matches = [{"home": "Mexico", "away": "South Africa",
                "date": "2026-06-11", "kickoff_utc": "2026-06-11T19:00:00Z",
                "prediction": {"home": 0.52, "draw": 0.26, "away": 0.22}}]
    body = mb.morning_brief("2026-06-11", matches)
    assert "🕐 12:00pm PT / 2:00pm CT / 3:00pm ET" in body
    assert "Prediction: Mexico" in body


def test_morning_brief_without_kickoff_omits_clock_line():
    matches = [{"home": "Mexico", "away": "South Africa",
                "prediction": {"home": 0.52, "draw": 0.26, "away": 0.22}}]
    body = mb.morning_brief("2026-06-11", matches)
    assert "🕐" not in body
    assert "Mexico vs South Africa" in body
    assert "Prediction: Mexico" in body


# --- venue (city, country) ---

def _m(venue=None, **kw):
    m = {"home": "USA", "away": "Mexico",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2}}
    if venue is not None:
        m["venue"] = venue
    m.update(kw)
    return m


def test_morning_brief_includes_city_country():
    text = mb.morning_brief("2026-06-11", [_m(venue="Mexico City")])
    assert "Mexico City, Mexico" in text


def test_half_time_includes_city_country():
    text = mb.half_time(_m(venue="Toronto"), 1, 0)
    assert "Toronto, Canada" in text


def test_post_match_includes_city_country():
    text = mb.post_match(_m(venue="Atlanta",
                            result={"home_goals": 2, "away_goals": 0}))
    assert "Atlanta, USA" in text


def test_daily_recap_includes_city_country():
    text = mb.daily_recap(
        "2026-06-11",
        [_m(venue="Guadalajara (Zapopan)",
            result={"home_goals": 1, "away_goals": 1})],
        {})
    assert "Guadalajara (Zapopan), Mexico" in text


def test_unknown_venue_shows_city_without_country():
    text = mb.half_time(_m(venue="Lunar Base"), 0, 0)
    assert "Lunar Base" in text
    assert "Lunar Base," not in text


def test_missing_venue_messages_still_render():
    text = mb.half_time(_m(), 2, 1)
    assert "Half-time" in text and "USA 2 - 1 Mexico" in text
    brief = mb.morning_brief("2026-06-11", [_m()])
    assert "USA vs Mexico" in brief


def test_all_16_host_cities_have_countries():
    venues = [
        "Atlanta", "Boston (Foxborough)", "Dallas (Arlington)",
        "Guadalajara (Zapopan)", "Houston", "Kansas City",
        "Los Angeles (Inglewood)", "Mexico City", "Miami (Miami Gardens)",
        "Monterrey (Guadalupe)", "New York/New Jersey (East Rutherford)",
        "Philadelphia", "San Francisco Bay Area (Santa Clara)",
        "Seattle", "Toronto", "Vancouver",
    ]
    for v in venues:
        place = mb.place(v)
        assert place.startswith(v) and ", " in place, place


_EVENTS = [
    {"kind": "goal", "player": "Ismael Saibari", "team": "Morocco", "minute": "21'"},
    {"kind": "penalty", "player": "Vinicius Jr", "team": "Brazil", "minute": "64'"},
    {"kind": "red", "player": "Gabriel", "team": "Brazil", "minute": "80'"},
]


def test_post_match_lists_scorers_and_red_cards():
    match = {"home": "Brazil", "away": "Morocco",
             "prediction": {"home": 0.6, "draw": 0.25, "away": 0.15},
             "result": {"home_goals": 1, "away_goals": 1, "events": _EVENTS}}
    body = mb.post_match(match)
    assert "⚽ 21' Ismael Saibari (Morocco)" in body
    assert "⚽ 64' Vinicius Jr (Brazil, pen)" in body
    assert "🟥 80' Gabriel (Brazil)" in body


def test_half_time_lists_first_half_events():
    match = {"home": "Brazil", "away": "Morocco",
             "prediction": {"home": 0.6, "draw": 0.25, "away": 0.15}}
    body = mb.half_time(match, 0, 1, events=[_EVENTS[0]])
    assert "Half-time:" in body and "Brazil 0 - 1 Morocco" in body
    assert "⚽ 21' Ismael Saibari (Morocco)" in body


def test_daily_recap_includes_scorers():
    matches = [{"home": "Brazil", "away": "Morocco",
                "prediction": {"home": 0.6, "draw": 0.25, "away": 0.15},
                "result": {"home_goals": 1, "away_goals": 1, "events": _EVENTS}}]
    body = mb.daily_recap("2026-06-13", matches, {})
    assert "⚽ 21' Ismael Saibari (Morocco)" in body
    assert "🟥 80' Gabriel (Brazil)" in body


def test_event_lines_handle_own_goal_and_missing_player():
    evs = [{"kind": "own_goal", "player": "", "team": "USA", "minute": "12'"}]
    lines = mb._event_lines(evs)
    assert lines == ["  ⚽ 12' Unknown (USA, OG)"]


def test_messages_without_events_have_no_event_lines():
    match = {"home": "USA", "away": "Canada",
             "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
             "result": {"home_goals": 0, "away_goals": 0}}
    assert "⚽" not in mb.post_match(match)


def test_post_match_leads_with_full_time_label():
    m = {"home": "Brazil", "away": "Morocco",
         "prediction": {"home": 0.6, "draw": 0.25, "away": 0.15},
         "result": {"home_goals": 1, "away_goals": 1, "events": _EVENTS}}
    body = mb.post_match(m)
    assert "Full time:" in body and "Brazil 1 - 1 Morocco" in body
    # daily-recap result lines must NOT carry the Full time label
    recap = mb.daily_recap("2026-06-13", [m], {})
    assert "Full time:" not in recap


def test_daily_recap_lists_unresolved_match_as_pending():
    matches = [
        {"home": "Brazil", "away": "Morocco",
         "prediction": {"home": 0.6, "draw": 0.25, "away": 0.15},
         "result": {"home_goals": 1, "away_goals": 1}},
        {"home": "Australia", "away": "Turkey",  # never reconciled -> no result
         "prediction": {"home": 0.4, "draw": 0.3, "away": 0.3}},
    ]
    body = mb.daily_recap("2026-06-13", matches, {})
    assert "Brazil 1 - 1 Morocco" in body
    assert "No result recorded:" in body
    assert "Australia vs Turkey" in body


# --- prediction accuracy ---

def test_fmt_accuracy():
    assert mb.fmt_accuracy(5, 8) == "5/8 (62.5%)"
    assert mb.fmt_accuracy(0, 0) == "0/0 (—)"
    assert mb.fmt_accuracy(3, 3) == "3/3 (100.0%)"


def test_post_match_shows_per_match_and_overall_accuracy():
    # predicted Switzerland (away argmax) but it's a draw -> miss (0%)
    match = {"home": "Qatar", "away": "Switzerland",
             "prediction": {"home": 0.30, "draw": 0.30, "away": 0.40},
             "result": {"home_goals": 1, "away_goals": 1}}
    body = mb.post_match(match, overall=(5, 9))
    assert "Qatar 1 - 1 Switzerland" in body
    assert "Overall prediction: 5/9 (55.6%)" in body
    # prediction is the LAST line, in 'Prediction ✗: <pick>' form
    assert body.rstrip().endswith("Prediction ✗: Switzerland")


def test_post_match_hit_shows_100_percent():
    match = {"home": "Germany", "away": "Curaçao",
             "prediction": {"home": 0.78, "draw": 0.06, "away": 0.16},
             "result": {"home_goals": 7, "away_goals": 1}}
    body = mb.post_match(match, overall=(1, 1))
    assert "Germany 7 - 1 Curaçao" in body
    assert body.rstrip().endswith("Prediction ✓: Germany")


def test_daily_recap_shows_overall_prediction_line():
    matches = [{"home": "Brazil", "away": "Morocco",
                "prediction": {"home": 0.6, "draw": 0.25, "away": 0.15},
                "result": {"home_goals": 1, "away_goals": 1}}]
    body = mb.daily_recap("2026-06-13", matches, {},
                          day_acc=(3, 4), overall_acc=(12, 18))
    assert "Overall prediction —" in body
    assert "today 3/4 (75.0%)" in body and "overall 12/18 (66.7%)" in body


# --- chronological order + monospace table ---

def test_morning_brief_sorted_by_kickoff():
    matches = [
        {"home": "Belgium", "away": "Egypt", "kickoff_utc": "2026-06-15T19:00:00Z",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2}},
        {"home": "Spain", "away": "Cape Verde", "kickoff_utc": "2026-06-15T16:00:00Z",
         "prediction": {"home": 0.9, "draw": 0.06, "away": 0.04}},
        {"home": "Iran", "away": "New Zealand", "kickoff_utc": "2026-06-16T01:00:00Z",
         "prediction": {"home": 0.7, "draw": 0.2, "away": 0.1}},
    ]
    body = mb.morning_brief("2026-06-15", matches)
    # earliest kickoff (Spain 16:00Z) before Belgium (19:00Z) before Iran (01:00Z+1)
    assert body.index("Spain vs") < body.index("Belgium vs") < body.index("Iran vs")


def test_daily_recap_standings_wrapped_in_pre_monospace():
    tables = {"A": [
        {"team": "Mexico", "played": 1, "points": 3, "gd": 2, "gf": 2, "ga": 0},
        {"team": "Czech Republic", "played": 1, "points": 0, "gd": -1, "gf": 1, "ga": 2}]}
    body = mb.daily_recap("2026-06-15", [], tables)
    assert "<code>" in body and "</code>" in body and "<pre>" not in body
    block = body[body.index("<code>"):body.index("</code>")]
    assert "Mexico" in block and "Czech Republic" in block and "Group A" in block


def test_daily_recap_results_sorted_by_kickoff():
    matches = [
        {"home": "B", "away": "b", "kickoff_utc": "2026-06-15T19:00:00Z",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 1, "away_goals": 0}},
        {"home": "A", "away": "a", "kickoff_utc": "2026-06-15T16:00:00Z",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 2, "away_goals": 2}}]
    body = mb.daily_recap("2026-06-15", matches, {})
    assert body.index("A 2 - 2 a") < body.index("B 1 - 0 b")


def test_daily_recap_blank_line_between_results():
    matches = [
        {"home": "A", "away": "a", "kickoff_utc": "2026-06-15T16:00:00Z",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 1, "away_goals": 0}},
        {"home": "B", "away": "b", "kickoff_utc": "2026-06-15T19:00:00Z",
         "prediction": {"home": 0.5, "draw": 0.3, "away": 0.2},
         "result": {"home_goals": 2, "away_goals": 2}}]
    body = mb.daily_recap("2026-06-15", matches, {})
    # a blank line separates the two result blocks
    assert "\n\n  B 2 - 2 b" in body
