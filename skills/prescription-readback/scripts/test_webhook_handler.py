from webhook_handler import handle_calle_event


def _payload(call_id="c1", event="call.completed", structured=None):
    return {
        "event": event,
        "metadata": {"call_id": call_id},
        "structured_result": structured if structured is not None else {"overall": "confirmed"},
    }


def test_duplicate_event_id_is_not_reprocessed():
    seen = set()
    calls = []

    def on_result(call_id, structured, transcript):
        calls.append(call_id)
        return "scheduled"

    first = handle_calle_event("evt1", _payload(), seen, on_result)
    second = handle_calle_event("evt1", _payload(), seen, on_result)

    assert first["status"] == "processed"
    assert first["disposition"] == "scheduled"
    assert second["status"] == "duplicate"
    assert len(calls) == 1


def test_missing_call_id_is_ignored():
    result = handle_calle_event(
        "evt1", {"event": "call.completed", "metadata": {}}, set(), lambda *a: None
    )
    assert result["status"] == "ignored"
    assert "call_id" in result["reason"]


def test_non_terminal_event_is_ignored():
    result = handle_calle_event(
        "evt1", {"event": "call.started", "metadata": {"call_id": "c1"}}, set(), lambda *a: None
    )
    assert result["status"] == "ignored"


def test_missing_event_id_still_processes_but_cannot_dedupe():
    calls = []
    result = handle_calle_event(None, _payload(), set(), lambda *a: calls.append(a) or "scheduled")
    assert result["status"] == "processed"
    assert len(calls) == 1


def test_failure_events_discard_claimed_confirmation():
    for event in ("call.failed", "call.result_validation_failed"):
        captured = []
        handle_calle_event("e", _payload(event=event), set(), lambda cid, result, transcript: captured.append(result))
        assert captured == [{}]
