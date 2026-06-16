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
    assert "Match-day updates, on Telegram." in html
    assert "https://t.me/Kipl26bot" in html
    assert "Start on Telegram" in html
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
    assert 'Mexico <span class="vs">vs</span> South Africa' in html
    assert "Jun 11 · Mexico City" in html
    assert "Mexico won 2-1" in html


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
    assert "<caption>Group A</caption>" in html
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
