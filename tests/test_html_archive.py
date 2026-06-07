from src import html_archive as ha


def test_render_includes_brand_fonts_and_messages(tmp_path):
    state = {"days": [{"date": "2026-06-11", "messages": [
        {"type": "morning_brief", "body": "USA vs Mexico", "sent": True}]}],
        "bracket": {"title_odds": {"Brazil": 0.18}}}
    out = tmp_path / "index.html"
    ha.render(state, out)
    html = out.read_text()
    assert "Playfair Display" in html and "USA vs Mexico" in html and "Brazil" in html


def test_render_uses_brand_background_color(tmp_path):
    out = tmp_path / "index.html"
    ha.render({"days": [], "bracket": {}}, out)
    assert "#F5F1EB" in out.read_text()


def test_render_lists_days_reverse_chronologically(tmp_path):
    state = {"days": [
        {"date": "2026-06-11", "messages": [{"type": "x", "body": "FIRST", "sent": True}]},
        {"date": "2026-06-12", "messages": [{"type": "x", "body": "SECOND", "sent": True}]}],
        "bracket": {}}
    out = tmp_path / "index.html"
    ha.render(state, out)
    html = out.read_text()
    assert html.index("SECOND") < html.index("FIRST")  # newest day first
