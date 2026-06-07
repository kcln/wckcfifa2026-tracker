from src import telegram_sender as ts

def test_send_posts_to_each_chat_id():
    calls = []
    poster = lambda url, data: calls.append(data) or type("R", (), {"ok": True})()
    ok = ts.send("hi", token="T", chat_ids=["1", "2"], poster=poster)
    assert ok and len(calls) == 2 and calls[0]["text"] == "hi"

def test_send_returns_false_on_exception():
    def boom(url, data): raise RuntimeError()
    assert ts.send("hi", token="T", chat_ids=["1"], poster=boom) is False

def test_send_noop_when_no_token():
    assert ts.send("hi", token="", chat_ids=["1"]) is False

def test_send_noop_when_no_chat_ids():
    assert ts.send("hi", token="T", chat_ids=[]) is False
