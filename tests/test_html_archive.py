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
    assert "<strong>Mexico</strong> 2-1 South Africa" in html


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
