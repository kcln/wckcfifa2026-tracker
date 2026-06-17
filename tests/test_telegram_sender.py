from src import telegram_sender as ts

def test_send_posts_to_each_chat_id_with_hyperlink_footer():
    calls = []
    poster = lambda url, data: calls.append(data) or type("R", (), {"ok": True})()
    ok = ts.send("hi", token="T", chat_ids=["1", "2"], poster=poster)
    assert ok and len(calls) == 2
    body = calls[0]["text"]
    assert body.startswith("hi")
    assert '<a href="https://kcln.github.io/wckcfifa2026-tracker/">' in body
    assert calls[0]["parse_mode"] == "HTML"


def test_send_html_escapes_body_but_not_link():
    calls = []
    poster = lambda url, data: calls.append(data) or type("R", (), {"ok": True})()
    ts.send("Bosnia & Herzegovina <3", token="T", chat_ids=["1"], poster=poster)
    body = calls[0]["text"]
    assert "Bosnia &amp; Herzegovina &lt;3" in body          # body escaped
    assert '<a href="https://kcln.github.io/wckcfifa2026-tracker/">' in body  # link intact

def test_send_returns_false_on_exception():
    def boom(url, data): raise RuntimeError()
    assert ts.send("hi", token="T", chat_ids=["1"], poster=boom) is False

def test_send_noop_when_no_token():
    assert ts.send("hi", token="", chat_ids=["1"]) is False

def test_send_noop_when_no_chat_ids():
    assert ts.send("hi", token="T", chat_ids=[]) is False


def test_send_preserves_code_block_no_pre_badge():
    calls = []
    poster = lambda url, data: calls.append(data) or type("R", (), {"ok": True})()
    ts.send("Standings:\n<code>Mexico & co  3</code>", token="T", chat_ids=["1"], poster=poster)
    body = calls[0]["text"]
    assert "<code>" in body and "</code>" in body        # code tags survive
    assert "Mexico &amp; co" in body                     # inner text still escaped


def _resp(ok, status=200):
    return type("R", (), {"ok": ok, "status_code": status})()


def test_send_attempts_all_recipients_even_if_one_is_blocked():
    # B blocked the bot (403). A and C must STILL be attempted (the old code
    # aborted at B, dropping C and re-spamming A forever).
    attempted = []

    def poster(url, data):
        cid = data["chat_id"]
        attempted.append(cid)
        return _resp(cid != "B", 200 if cid != "B" else 403)

    dead = []
    res = ts.send("hi", token="T", chat_ids=["A", "B", "C"],
                  poster=poster, on_dead=dead.append)
    assert attempted == ["A", "B", "C"]   # never aborted
    assert dead == ["B"]                   # B flagged permanently dead
    assert res is True                     # no transient failure → mark sent


def test_send_transient_failure_returns_false_but_tries_everyone():
    attempted = []

    def poster(url, data):
        cid = data["chat_id"]
        attempted.append(cid)
        return _resp(cid != "B", 200 if cid != "B" else 500)   # 500 = transient

    res = ts.send("hi", token="T", chat_ids=["A", "B", "C"], poster=poster)
    assert attempted == ["A", "B", "C"]   # still attempted all
    assert res is False                    # transient → retry next cycle


def test_send_network_error_on_one_does_not_skip_the_rest():
    attempted = []

    def poster(url, data):
        cid = data["chat_id"]
        attempted.append(cid)
        if cid == "B":
            raise RuntimeError("network blip")
        return _resp(True)

    res = ts.send("hi", token="T", chat_ids=["A", "B", "C"], poster=poster)
    assert attempted == ["A", "B", "C"]   # B's exception didn't abort the loop
    assert res is False                    # transient → retry
