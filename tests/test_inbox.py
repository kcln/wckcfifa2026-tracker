from src import inbox


def _harness(subs, approver="99"):
    sent = []        # (chat_id, text, has_markup)
    answered = []    # (cq_id, text)
    catchups = {1: ["brief", "update", "recap"], 2: ["brief"],
                3: ["update"], 4: ["recap"]}

    def send(chat_id, text, reply_markup=None):
        sent.append((str(chat_id), text, reply_markup is not None))

    def answer_cb(cq_id, text=""):
        answered.append((cq_id, text))

    def run(updates):
        return inbox.process_updates(
            updates, subs, approver=approver, send=send, answer_cb=answer_cb,
            catchup=lambda o: catchups[o], now_ts="T")

    return run, sent, answered


def _start(uid, chat_id, name="Ann"):
    return {"update_id": uid,
            "message": {"chat": {"id": int(chat_id), "first_name": name},
                        "text": "/start"}}


def test_start_adds_pending_and_notifies_approver():
    subs = {"approved": [], "pending": {}, "onboarded": [], "last_update_id": 0}
    run, sent, _ = _harness(subs)
    run([_start(5, "777", "Ravi")])
    assert "777" in subs["pending"]
    # approver got a prompt WITH inline buttons
    assert sent and sent[0][0] == "99" and sent[0][2] is True
    assert "Ravi" in sent[0][1] and "777" in sent[0][1]
    assert subs["last_update_id"] == 5


def test_approve_callback_promotes_and_onboards():
    subs = {"approved": [], "pending": {"777": {"ts": "T"}},
            "onboarded": [], "last_update_id": 5}
    run, sent, answered = _harness(subs)
    run([{"update_id": 6, "callback_query": {
        "id": "cq1", "from": {"id": 99}, "data": "approve:777"}}])
    assert "777" in subs["approved"] and "777" not in subs["pending"]
    assert answered == [("cq1", "Approved ✅")]
    # the onboarding menu was sent to the new member
    assert any(c == "777" and "Reply with a number" in t for c, t, _ in sent)


def test_deny_callback_drops_pending():
    subs = {"approved": [], "pending": {"777": {"ts": "T"}},
            "onboarded": [], "last_update_id": 5}
    run, sent, answered = _harness(subs)
    run([{"update_id": 7, "callback_query": {
        "id": "cq2", "from": {"id": 99}, "data": "deny:777"}}])
    assert "777" not in subs["pending"] and subs["approved"] == []
    assert answered == [("cq2", "Declined")]


def test_callback_from_non_approver_ignored():
    subs = {"approved": [], "pending": {"777": {"ts": "T"}},
            "onboarded": [], "last_update_id": 0}
    run, sent, answered = _harness(subs)
    run([{"update_id": 8, "callback_query": {
        "id": "cq3", "from": {"id": 12345}, "data": "approve:777"}}])
    assert subs["approved"] == [] and "777" in subs["pending"]
    assert answered == [("cq3", "")]   # acknowledged but no action


def test_onboarding_choice_sends_catchup_once():
    subs = {"approved": ["777"], "pending": {}, "onboarded": [],
            "last_update_id": 0}
    run, sent, _ = _harness(subs)
    run([{"update_id": 9, "message": {"chat": {"id": 777}, "text": "1"}}])
    bodies = [t for c, t, _ in sent if c == "777"]
    assert bodies == ["brief", "update", "recap"]
    assert "777" in subs["onboarded"]
    # a second number reply does nothing (already onboarded)
    sent.clear()
    run([{"update_id": 10, "message": {"chat": {"id": 777}, "text": "2"}}])
    assert sent == []


def test_stop_unsubscribes():
    subs = {"approved": ["777"], "pending": {}, "onboarded": ["777"],
            "last_update_id": 0}
    run, sent, _ = _harness(subs)
    run([{"update_id": 11, "message": {"chat": {"id": 777}, "text": "/stop"}}])
    assert subs["approved"] == [] and subs["onboarded"] == []


def test_start_ignored_when_already_known():
    subs = {"approved": ["777"], "pending": {}, "onboarded": ["777"],
            "last_update_id": 0}
    run, sent, _ = _harness(subs)
    run([_start(12, "777")])
    assert sent == []   # no duplicate approval prompt


def test_start_does_not_persist_name_in_pending():
    # pending entries are committed to the public repo — the name must only
    # appear in the transient approval prompt, never in subscribers.json
    subs = {"approved": [], "pending": {}, "onboarded": [], "last_update_id": 0}
    run, sent, _ = _harness(subs)
    run([_start(5, "777", "Ravi Kumar")])
    assert "name" not in subs["pending"]["777"]
    assert any("Ravi Kumar" in t for _, t, _m in sent)   # prompt still names them


def test_approve_dms_approver_a_confirmation_with_name():
    subs = {"approved": [], "pending": {"777": {"ts": "T", "name": "Ravi Kumar"}},
            "onboarded": [], "last_update_id": 5}
    run, sent, _ = _harness(subs)            # approver == "99"
    run([{"update_id": 6, "callback_query": {
        "id": "cq1", "from": {"id": 99}, "data": "approve:777"}}])
    # approver got a plain confirmation naming the new member
    assert any(c == "99" and "Ravi Kumar" in t and "added" in t
               and m is False for c, t, m in sent)


def test_approve_confirmation_falls_back_to_chat_id_without_name():
    subs = {"approved": [], "pending": {}, "onboarded": [], "last_update_id": 5}
    run, sent, _ = _harness(subs)
    run([{"update_id": 6, "callback_query": {
        "id": "cq1", "from": {"id": 99}, "data": "approve:777"}}])
    assert "777" in subs["approved"]
    assert any(c == "99" and "777" in t and "added" in t for c, t, _ in sent)
