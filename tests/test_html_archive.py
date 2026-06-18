import json
import re

from src import html_archive as ha


def _render(state, tmp_path):
    out = tmp_path / "index.html"
    ha.render(state, out)
    return out.read_text()


def test_render_replicates_ipl_archive_design(tmp_path):
    html = _render({"days": [], "bracket": {}}, tmp_path)
    # Purple "Every match. Every prediction." design, not Bauhaus
    assert "Every match." in html and "Every <span class=\"grad\">prediction." in html
    assert "#F8F5F1" in html          # warm paper background
    assert "--p-700: #7E22CE" in html  # purple scale
    assert "Outfit" in html and "Work+Sans" in html
    assert "lion-transparent.png" in html
    assert "World Cup 2026 · Daily tracker" in html


def test_render_has_telegram_cta_and_no_signup_form(tmp_path):
    html = _render({"days": [], "bracket": {}}, tmp_path)
    assert "Tap Start on" in html and "WcFifa2026tracker" in html
    assert "https://t.me/Kipl26bot" in html
    assert "Start on Telegram" in html
    # the dark "Match-day updates" pitch panel was removed
    assert "Match-day updates, on Telegram." not in html
    assert '<div class="signup-pitch">' not in html
    # The phone sign-up form must NOT exist (Telegram CTA replaced it)
    assert "<form" not in html
    assert "Sign up" not in html
    assert 'input' not in html


def test_render_hero_defaults_pre_tournament(tmp_path):
    html = _render({"days": [], "bracket": {}}, tmp_path)
    assert "Match data loading…" in html
    assert "Title odds loading…" in html
    assert "__HERO_MATCH__" not in html  # no raw tokens ever visible


def test_render_hero_leader_from_title_odds(tmp_path):
    state = {"days": [], "bracket": {"title_odds": {"Argentina": 0.207,
                                                    "Spain": 0.158}}}
    html = _render(state, tmp_path)
    assert 'id="hero-leader">Argentina<' in html
    assert "20.7% title odds" in html


def test_render_hero_most_recent_from_last_result(tmp_path):
    state = {"days": [], "bracket": {},
             "last_result": {"home": "Mexico", "away": "South Africa",
                             "home_goals": 2, "away_goals": 1,
                             "date": "2026-06-11", "venue": "Mexico City"}}
    html = _render(state, tmp_path)
    assert '<span class="tm">Mexico</span><span class="sc">2</span>' in html
    assert '<span class="sc">1</span><span class="tm">South Africa</span>' in html
    assert "Jun 11 · Mexico City" in html
    assert "Mexico won" not in html   # old separate result line killed


def test_render_days_newest_first_only_newest_open(tmp_path):
    state = {"days": [
        {"date": "2026-06-11", "messages": [
            {"type": "morning_brief", "body": "FIRST", "sent": True}]},
        {"date": "2026-06-12", "messages": [
            {"type": "morning_brief", "body": "SECOND", "sent": True}]}],
        "bracket": {}}
    html = _render(state, tmp_path)
    assert html.index("SECOND") < html.index("FIRST")
    assert '<details data-day="2026-06-12" open>' in html
    assert '<details data-day="2026-06-11">' in html
    assert "Friday, June 12, 2026" in html  # long day header
    assert "Day 2 of 39" in html


def test_render_article_tags_match_message_types(tmp_path):
    msgs = [{"type": t, "body": t, "sent": True} for t in
            ("morning_brief", "post_match", "daily_recap", "bracket_update")]
    state = {"days": [{"date": "2026-06-11", "messages": msgs}], "bracket": {}}
    html = _render(state, tmp_path)
    assert 'class="tag morning">Morning brief<' in html
    assert 'class="tag result">Match result<' in html
    assert 'class="tag recap">Day recap<' in html
    assert 'class="tag phase">Bracket update<' in html


def test_render_bolds_winner_in_result_lines(tmp_path):
    body = "Mexico 2-1 South Africa  ✓  (Prediction: Mexico)"
    state = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "post_match", "body": body, "sent": True}]}], "bracket": {}}
    html = _render(state, tmp_path)
    assert "<strong>Mexico</strong> 2 - 1 South Africa" in html


def test_render_bolds_pick_in_morning_brief(tmp_path):
    body = "Mexico vs South Africa  |  Prediction: Mexico  |  Home 52.0%"
    state = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "morning_brief", "body": body, "sent": True}]}], "bracket": {}}
    html = _render(state, tmp_path)
    assert "Prediction: <strong>Mexico</strong>" in html


def test_render_escapes_html_in_bodies(tmp_path):
    state = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "daily_recap", "body": "<script>alert(1)</script>",
         "sent": True}]}], "bracket": {}}
    html = _render(state, tmp_path)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_half_time_gets_phase_tag(tmp_path):
    state = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "half_time", "body": "Half-time: Mexico 1-0 South Africa",
         "sent": True}]}], "bracket": {}}
    html = _render(state, tmp_path)
    assert 'class="tag phase">Half-time<' in html


def test_render_when_stack_shows_kickoff_in_four_zones(tmp_path):
    state = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "post_match", "body": "Mexico 2-1 South Africa  ✓  (Prediction: Mexico)",
         "sent": True, "kickoff_utc": "2026-06-11T19:00:00Z"}]}], "bracket": {}}
    html = _render(state, tmp_path)
    assert ("<span>12:00pm PT</span><span>2:00pm CT</span>"
            "<span>3:00pm ET</span><span>12:30am IST</span>") in html


def test_render_when_stack_empty_without_kickoff(tmp_path):
    state = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "morning_brief", "body": "x", "sent": True}]}], "bracket": {}}
    html = _render(state, tmp_path)
    assert '<span class="when"></span>' in html


def test_render_pre_block_becomes_monospace_element(tmp_path):
    body = "Group Standings:\n<code>Group A\nMexico  3\n</code>"
    state = {"days": [{"date": "2026-06-15", "messages": [
        {"type": "daily_recap", "body": body, "sent": True}]}], "bracket": {}}
    html = _render(state, tmp_path)
    assert '<pre class="mono">' in html and "Mexico  3" in html
    assert "&lt;code&gt;" not in html  # the literal tag never leaks to the page


# --- Option 3: structured board + standings rendering ---

def test_render_standings_as_real_html_table(tmp_path):
    state = {"days": [], "bracket": {}, "groups": {
        "A": [
            {"team": "Mexico", "played": 1, "points": 3, "gd": 2, "gf": 2, "ga": 0},
            {"team": "South Korea", "played": 1, "points": 3, "gd": 1, "gf": 2, "ga": 1},
            {"team": "Czech Republic", "played": 1, "points": 0, "gd": -1, "gf": 1, "ga": 2},
        ]}}
    html = _render(state, tmp_path)
    assert '<table class="gtable">' in html
    assert "<summary>Group A</summary>" in html
    assert '<td class="t-team">Mexico</td>' in html
    assert '<td class="t-pts">3</td>' in html
    assert 'class="qual"' in html              # top-2 highlighted
    assert "&lt;code&gt;" not in html and "<pre" not in html  # no ASCII table


def test_render_board_match_cards(tmp_path):
    state = {"days": [], "bracket": {}, "groups": {},
             "board": [{"date": "2026-06-15", "matches": [
                 {"id": "1", "home": "Belgium", "away": "Egypt",
                  "kickoff_utc": "2026-06-15T19:00:00Z", "venue": "Seattle",
                  "stage": "group", "status": "FT", "hg": 1, "ag": 1,
                  "events": [{"kind": "goal", "player": "Ashour",
                              "team": "Egypt", "minute": "20'"}],
                  "hit": False,
                  "pred": {"home": 0.48, "draw": 0.30, "away": 0.22,
                           "pick": "Belgium"}}]}]}
    html = _render(state, tmp_path)
    assert '<div class="mcard">' in html
    assert ">Belgium<" in html and ">Egypt<" in html
    assert '<span class="sc">1</span>' in html        # score
    assert 'Prediction: <span class="miss">Belgium</span>' in html
    assert 'class="pill no">✗' in html               # missed prediction
    assert '<div class="oddsbar"' in html            # odds bar
    assert "Ashour" in html                          # scorer
    assert "Seattle, USA" in html                    # venue formatted


def _day17():
    return [
        {"id": "a", "home": "Portugal", "away": "DR Congo",
         "kickoff_utc": "2026-06-17T17:00:00Z", "venue": "Houston",
         "status": "FT", "hg": 1, "ag": 1, "events": [],
         "pred": {"home": .6, "draw": .25, "away": .15, "pick": "Portugal"}},
        {"id": "d", "home": "England", "away": "Croatia",
         "kickoff_utc": "2026-06-17T20:00:00Z", "venue": "Dallas (Arlington)",
         "status": "sched", "hg": 2, "ag": 2,
         "pred": {"home": .29, "draw": .28, "away": .43, "pick": "Croatia"}},
        {"id": "b", "home": "Ghana", "away": "Panama",
         "kickoff_utc": "2026-06-17T23:00:00Z", "venue": "Toronto",
         "status": "sched",
         "pred": {"home": .3, "draw": .2, "away": .5, "pick": "Panama"}},
        {"id": "c", "home": "Uzbekistan", "away": "Colombia",
         "kickoff_utc": "2026-06-18T02:00:00Z", "venue": "Mexico City",
         "status": "sched",
         "pred": {"home": .2, "draw": .25, "away": .55, "pick": "Colombia"}}]


def test_board_day_no_live_is_reverse_chronological(tmp_path):
    # No live match: pure reverse chronological, latest kickoff on top.
    state = {"days": [], "bracket": {}, "groups": {},
             "board": [{"date": "2026-06-17", "matches": _day17()}]}
    html = _render(state, tmp_path)
    assert (html.index("Uzbekistan") < html.index("Ghana")
            < html.index("England") < html.index("Portugal"))


def test_board_day_live_match_pinned_then_upcoming_soonest_then_done(tmp_path):
    # England live: pinned on top, then upcoming soonest-first (Ghana 4pm before
    # Uzbekistan 7pm), then the finished match (Portugal) at the bottom.
    day = _day17()
    next(m for m in day if m["id"] == "d")["status"] = "live"
    state = {"days": [], "bracket": {}, "groups": {},
             "board": [{"date": "2026-06-17", "matches": day}]}
    html = _render(state, tmp_path)
    assert (html.index("England") < html.index("Ghana")
            < html.index("Uzbekistan") < html.index("Portugal"))


def _sched_state():
    return {"days": [], "bracket": {}, "groups": {}, "schedule": [
        {"date": "2026-06-15", "matches": [
            {"id": "1", "home": "Spain", "away": "Japan", "stage": "group",
             "kickoff_utc": "2026-06-15T19:00:00Z", "venue": "Atlanta",
             "status": "FT", "hg": 2, "ag": 0, "events": [], "hit": True,
             "pred": {"home": .6, "draw": .25, "away": .15, "pick": "Spain"}}]},
        {"date": "2026-06-17", "matches": [
            {"id": "2", "home": "England", "away": "Croatia", "stage": "group",
             "kickoff_utc": "2026-06-17T20:00:00Z", "venue": "Dallas (Arlington)",
             "status": "live", "hg": 3, "ag": 2, "clock": "84'", "events": [],
             "pred": {"home": .29, "draw": .28, "away": .43, "pick": "Croatia"}}]},
        {"date": "2026-06-20", "matches": [
            {"id": "3", "home": "Spain", "away": "England", "stage": "group",
             "kickoff_utc": "2026-06-20T19:00:00Z", "venue": "Seattle",
             "status": "sched",
             "pred": {"home": .4, "draw": .3, "away": .3, "pick": "Spain"}}]},
        {"date": "2026-06-28", "matches": [
            {"id": "73", "home": "2A", "away": "2B", "stage": "R32",
             "kickoff_utc": "2026-06-28T19:00:00Z", "venue": "Boston (Foxborough)",
             "status": "sched"}]}]}


def test_schedule_is_by_day_strip(tmp_path):
    html = _render(_sched_state(), tmp_path)
    assert '<span class="sec-h">Schedule</span>' in html
    assert '<div class="daystrip">' in html
    # strip = group-stage days only, ascending; Jun 28+ knockouts go in the bracket
    for date in ("2026-06-15", "2026-06-17", "2026-06-20"):
        assert f'data-date="{date}"' in html
    i = [html.index(f'data-date="{d}"')
         for d in ("2026-06-15", "2026-06-17", "2026-06-20")]
    assert i == sorted(i)
    assert 'data-date="2026-06-28"' not in html   # knockout day not a strip column
    assert '<div class="bk">' in html             # bracket appended to the right
    for gone in ("Today", "Upcoming", "Finished", "Bracket"):
        assert f'<span class="sub-h">{gone}</span>' not in html


def test_schedule_today_column_highlighted(tmp_path):
    # current day = latest day with a live match (Jun 17, England live)
    html = _render(_sched_state(), tmp_path)
    assert '<div class="daycol is-today" data-date="2026-06-17">' in html


def test_schedule_box_shows_score_live_minute_and_location_no_scorers(tmp_path):
    html = _render(_sched_state(), tmp_path)
    # live box: score + live dot + minute, location, but no scorer list/odds bar
    assert '<span class="dsc">3</span>' in html and '<span class="dsc">2</span>' in html
    assert 'class="dbox-meta"><span class="livedot"></span>84' in html
    assert 'Dallas (Arlington), USA' in html
    # the strip carries no scorer lists, odds bars, or round-bracket columns
    strip = re.search(r'<div class="daystrip">.*?</div></div></details>', html, re.S)
    assert strip is not None
    assert '<ul class="scorers">' not in strip.group(0)
    assert '<div class="oddsbar"' not in strip.group(0)
    assert '<div class="bracket">' not in html


def test_schedule_strip_upcoming_kickoff_and_knockout_in_bracket(tmp_path):
    html = _render(_sched_state(), tmp_path)
    assert "pm PT" in html                       # strip upcoming kickoff label
    # knockout slots now render in the bracket (unresolved here: no groups data)
    assert '<div class="bk">' in html
    assert '<span class="bkm-nm">2A</span>' in html
    assert '<span class="bkm-nm">2B</span>' in html


def test_no_schedule_state_renders_no_section(tmp_path):
    html = _render({"days": [], "bracket": {}, "groups": {}}, tmp_path)
    assert '<span class="sec-h">Schedule</span>' not in html


def test_render_board_scheduled_match_shows_upcoming(tmp_path):
    state = {"days": [], "bracket": {}, "groups": {},
             "board": [{"date": "2026-06-20", "matches": [
                 {"id": "9", "home": "Brazil", "away": "Serbia",
                  "kickoff_utc": "2026-06-20T19:00:00Z", "venue": "Atlanta",
                  "stage": "group", "status": "sched",
                  "pred": {"home": 0.6, "draw": 0.25, "away": 0.15,
                           "pick": "Brazil"}}]}]}
    html = _render(state, tmp_path)
    assert 'class="pill soon">upcoming' in html
    assert '<span class="vsbig">vs</span>' in html


def test_card_bolds_pick_only_on_correct_prediction(tmp_path):
    base = {"id": "1", "home": "Germany", "away": "Curaçao",
            "kickoff_utc": "2026-06-14T17:00:00Z", "venue": "Houston",
            "stage": "group", "status": "FT",
            "pred": {"home": 0.778, "draw": 0.063, "away": 0.159, "pick": "Germany"}}
    hit = {**base, "hg": 7, "ag": 1, "events": [], "hit": True}
    miss = {**base, "hg": 0, "ag": 1, "events": [], "hit": False}
    html_hit = _render({"days": [], "bracket": {}, "groups": {},
                        "board": [{"date": "2026-06-14", "matches": [hit]}]}, tmp_path)
    assert '<strong class="hit">Germany</strong>' in html_hit
    html_miss = _render({"days": [], "bracket": {}, "groups": {},
                         "board": [{"date": "2026-06-14", "matches": [miss]}]}, tmp_path)
    assert '<span class="miss">Germany</span>' in html_miss
    # odds labels are sized to their segment so they centre over it
    assert 'flex-basis:77.8%' in html_hit and 'flex-basis:15.9%' in html_hit


def test_sections_and_groups_are_collapsible_and_default_collapsed(tmp_path):
    state = {"days": [{"date": "2026-06-15", "messages": []}], "bracket": {},
             "groups": {"A": [{"team": "Mexico", "played": 1, "points": 3,
                               "gd": 2, "gf": 2, "ga": 0}]},
             "board": [{"date": "2026-06-15", "matches": [
                 {"id": "1", "home": "A", "away": "B", "status": "sched",
                  "kickoff_utc": "", "venue": "",
                  "pred": {"home": 0.5, "draw": 0.3, "away": 0.2, "pick": "A"}}]}]}
    html = _render(state, tmp_path)
    # whole sections are collapsible; Group standings collapsed, Match log open
    assert '<details class="section">' in html        # standings (collapsed)
    assert '<details class="section" open>' in html   # match log (open)
    assert '<span class="sec-h">Group standings</span>' in html
    assert '<span class="sec-h">Match log</span>' in html
    # per-group collapsed; the single (today's) day opens by default
    assert '<details class="grp">' in html
    assert '<details class="day" data-day="2026-06-15" open>' in html
    # expand/collapse-all controls for each scope + the toggle script
    assert 'data-act="expand" data-scope="groups"' in html
    assert 'data-act="collapse" data-scope="days"' in html
    assert "querySelectorAll(sel)" in html


def test_standings_has_definitions_legend_not_abbreviation_chip(tmp_path):
    state = {"days": [], "bracket": {}, "groups": {"A": [
        {"team": "Mexico", "played": 1, "points": 3, "gd": 2, "gf": 2, "ga": 0}]}}
    html = _render(state, tmp_path)
    assert "P = Played · Pts = Points · GD = Goal Difference" in html
    assert "GF = Goals For · GA = Goals Against" in html
    assert '<span class="count">P · Pts · GD' not in html   # old chip removed


def test_signup_cta_duplicated_top_and_bottom(tmp_path):
    html = _render({"days": [], "bracket": {}, "groups": {}}, tmp_path)
    assert html.count("Tap Start on") == 2          # top + bottom
    assert 'id="signup-top"' in html and 'id="signup"' in html


def test_today_status_open_on_first_render(tmp_path):
    state = {"days": [{"date": "2026-06-15", "messages": []},
                      {"date": "2026-06-16", "messages": []}],
             "bracket": {}, "groups": {},
             "board": [
                 {"date": "2026-06-15", "matches": [
                     {"id": "1", "home": "A", "away": "B", "status": "sched",
                      "kickoff_utc": "", "venue": "",
                      "pred": {"home": 0.5, "draw": 0.3, "away": 0.2, "pick": "A"}}]},
                 {"date": "2026-06-16", "matches": [
                     {"id": "2", "home": "C", "away": "D", "status": "sched",
                      "kickoff_utc": "", "venue": "",
                      "pred": {"home": 0.5, "draw": 0.3, "away": 0.2, "pick": "C"}}]}]}
    html = _render(state, tmp_path)
    # Match log section open, and today's (newest) day open; older day collapsed
    assert '<details class="section" open>' in html
    assert '<details class="day" data-day="2026-06-16" open>' in html
    assert '<details class="day" data-day="2026-06-15">' in html  # no open


def test_hero_features_live_match_and_autorefresh(tmp_path):
    state = {"days": [], "bracket": {}, "groups": {},
             "live": [{"id": "9", "home": "Argentina", "away": "Algeria",
                       "date": "2026-06-16", "venue": "Boston (Foxborough)",
                       "kickoff_utc": "2026-06-16T22:00:00Z",
                       "hg": 1, "ag": 0, "status": "LIVE", "clock": "50'",
                       "events": [{"kind": "goal", "player": "Lionel Messi",
                                   "team": "Argentina", "minute": "23'"}]}],
             "last_result": {"home": "Iraq", "away": "Norway", "home_goals": 1,
                             "away_goals": 4, "date": "2026-06-16"}}
    html = _render(state, tmp_path)
    # Score is rendered as discrete spans so flex gap spaces both sides evenly.
    assert '<span class="tm">Argentina</span><span class="sc">1</span>' in html
    assert '<span class="sc">0</span><span class="tm">Algeria</span>' in html
    assert "Live now" in html and "50&#x27;" in html   # clock in the kicker
    # Goal scorers (player + minute) appear in the hero, like the recap.
    assert "Lionel Messi" in html and "23&#x27;" in html
    # The hero refreshes client-side by polling live.json (no full-page meta
    # reload), so the slot is never frozen between page loads.
    assert '<meta http-equiv="refresh"' not in html
    assert "live.json?t=" in html and "setInterval(poll, 30000)" in html


def test_render_writes_live_json_for_live_match(tmp_path):
    state = {"days": [], "bracket": {}, "groups": {},
             "live": [{"id": "9", "home": "Argentina", "away": "Algeria",
                       "date": "2026-06-16", "venue": "Boston (Foxborough)",
                       "hg": 1, "ag": 0, "status": "LIVE", "clock": "50'"}]}
    _render(state, tmp_path)
    payload = json.loads((tmp_path / "live.json").read_text())
    assert payload == {"live": True, "id": "9", "home": "Argentina",
                       "away": "Algeria", "hg": 1, "ag": 0, "status": "LIVE",
                       "clock": "50'", "date": "2026-06-16",
                       "venue": "Boston (Foxborough)", "events": []}


def test_render_writes_live_json_fallback_to_last_result(tmp_path):
    state = {"days": [], "bracket": {}, "groups": {}, "live": [],
             "last_result": {"home": "Austria", "away": "Jordan",
                             "home_goals": 3, "away_goals": 1,
                             "date": "2026-06-16",
                             "venue": "San Francisco Bay Area (Santa Clara)"}}
    _render(state, tmp_path)
    payload = json.loads((tmp_path / "live.json").read_text())
    assert payload["live"] is False
    assert payload["home"] == "Austria" and payload["hg"] == 3 and payload["ag"] == 1


def test_render_writes_empty_live_json_when_no_match(tmp_path):
    _render({"days": [], "bracket": {}, "groups": {}}, tmp_path)
    assert json.loads((tmp_path / "live.json").read_text()) == {"live": False}


def test_card_shows_live_score_and_pill(tmp_path):
    state = {"days": [], "bracket": {}, "groups": {},
             "board": [{"date": "2026-06-16", "matches": [
                 {"id": "9", "home": "Argentina", "away": "Algeria",
                  "status": "live", "hg": 1, "ag": 0, "clock": "50'", "ht": False,
                  "kickoff_utc": "", "venue": "Boston (Foxborough)", "events": [],
                  "pred": {"home": 0.7, "draw": 0.2, "away": 0.1, "pick": "Argentina"}}]}]}
    html = _render(state, tmp_path)
    assert 'class="pill live"' in html and "50&#x27;" in html
    assert '<span class="sc">1</span>' in html


def _ko_state():
    return {"days": [], "bracket": {},
            "groups": {"A": [{"team": "Mexico", "played": 3, "points": 9,
                              "gd": 5, "gf": 6, "ga": 1},
                             {"team": "South Korea", "played": 3, "points": 6,
                              "gd": 2, "gf": 4, "ga": 2}]},
            "schedule": [
                {"date": "2026-06-20", "matches": [
                    {"id": "30", "home": "Mexico", "away": "South Korea",
                     "stage": "group", "kickoff_utc": "2026-06-20T19:00:00Z",
                     "venue": "Atlanta", "status": "FT", "hg": 2, "ag": 0,
                     "events": [], "pred": {"home": .6, "draw": .2, "away": .2,
                                            "pick": "Mexico"}}]},
                {"date": "2026-06-28", "matches": [
                    {"id": "73", "home": "2A", "away": "2B", "stage": "R32",
                     "kickoff_utc": "2026-06-28T19:00:00Z",
                     "venue": "Los Angeles (Inglewood)", "status": "sched"}]},
                {"date": "2026-07-19", "matches": [
                    {"id": "104", "home": "W101", "away": "W102",
                     "stage": "final", "kickoff_utc": "2026-07-19T19:00:00Z",
                     "venue": "New York/New Jersey (East Rutherford)",
                     "status": "sched"}]}]}


def test_schedule_shows_strip_and_bracket_together(tmp_path):
    # Both visible at once now (no date gate): group strip + knockout bracket,
    # with the divider between them.
    out = tmp_path / "index.html"
    ha.render(_ko_state(), out, today="2026-06-20")
    html = out.read_text()
    assert '<div class="daystrip">' in html        # group strip
    assert '<div class="bk">' in html              # AND the bracket
    assert '<div class="sched-div">' in html       # divider between them
    assert 'data-date="2026-06-20"' in html        # group day is a strip column


def test_schedule_bracket_resolves_slots_and_shows_location(tmp_path):
    out = tmp_path / "index.html"
    ha.render(_ko_state(), out, today="2026-06-28")
    html = out.read_text()
    assert '<div class="bk">' in html
    # group-slot tokens resolve to live country codes
    assert '<span class="bkm-nm">KOR</span>' in html   # 2A -> South Korea
    assert "Round of 32" in html and "Final" in html
    # location shown in bracket boxes
    assert "Los Angeles (Inglewood), USA" in html
    # the knockout day is NOT a strip column (it's only in the bracket)
    assert 'data-date="2026-06-28"' not in html
    assert '<span class="bkm-nm">2A</span>' not in html   # resolved, not raw token


def _proj_state(played):
    def r(team):
        return {"team": team, "played": played, "points": 0,
                "gd": 0, "gf": 0, "ga": 0}
    return {"days": [], "bracket": {},
            "groups": {"A": [r("Mexico"), r("South Korea"),
                             r("Czechia"), r("RSA")]},
            "schedule": [{"date": "2026-06-28", "matches": [
                {"id": "73", "home": "2A", "away": "2B", "stage": "R32",
                 "kickoff_utc": "2026-06-28T19:00:00Z", "venue": "Atlanta",
                 "status": "sched"}]}]}


def test_bracket_projects_whole_group_in_order_when_undecided(tmp_path):
    out = tmp_path / "i.html"
    ha.render(_proj_state(1), out)        # group A incomplete -> projected
    html = out.read_text()
    # 2A slot shows all of group A in standings order, faded
    assert '<span class="bkm-nm">MEX / KOR / CZE / RSA</span>' in html
    assert 'class="bkm-row proj"' in html                 # faded/projected
    assert "projected" in html                            # explanatory caption


def test_bracket_collapses_to_qualifier_when_group_decided(tmp_path):
    out = tmp_path / "i.html"
    ha.render(_proj_state(3), out)        # group A complete -> locked
    html = out.read_text()
    # collapses to the single runner-up, solid (not faded)
    kor = re.search(r'<div class="bkm-row[^"]*"><span class="bkm-nm">KOR</span>',
                    html)
    assert kor is not None and "proj" not in kor.group(0)
    assert 'MEX / KOR' not in html        # no longer the projected group list
