"""Framework-agnostic handling for CALL-E terminal call events.

Bind this to whatever you actually use — FastAPI, Flask, a serverless
handler — by wrapping it: read the event id header and JSON body your
framework gives you, call this function, return its result. This function
itself imports nothing framework-specific.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Set

TERMINAL_EVENTS = frozenset({"call.completed", "call.failed", "call.result_validation_failed"})

OnResult = Callable[[str, Dict[str, Any], list], Any]


def handle_calle_event(
    event_id: Optional[str],
    payload: Dict[str, Any],
    seen_event_ids: Set[str],
    on_result: OnResult,
) -> Dict[str, Any]:
    """Process one CALL-E terminal event. Idempotent on event_id.

    Args:
        event_id:       the CALL-E-Event-Id header value, or None.
        payload:        the webhook's JSON body.
        seen_event_ids: a set-like object you persist across calls — a
                         DB-backed set in production, a plain set() in
                         tests. This function only reads and writes it,
                         it doesn't own storage.
        on_result:      called as on_result(call_id, structured_result,
                         transcript) for a new, non-duplicate terminal
                         event. Whatever it returns becomes this
                         function's "disposition".

    metadata.call_id is the only reliable correlation key on the return
    path — CALL-E's own call id usually is not known to your system when
    the result arrives.
    """
    event_type = payload.get("event", "")
    if event_type not in TERMINAL_EVENTS:
        return {"status": "ignored", "reason": f"unhandled event type {event_type}"}

    call_id = (payload.get("metadata") or {}).get("call_id")
    if not call_id:
        return {"status": "ignored", "reason": "missing metadata.call_id"}

    if event_id and event_id in seen_event_ids:
        return {"status": "duplicate"}
    if event_id:
        seen_event_ids.add(event_id)

    structured = (payload.get("structured_result") or {}) if event_type == "call.completed" else {}
    transcript = payload.get("transcript") or []
    disposition = on_result(call_id, structured, transcript)

    return {"status": "processed", "disposition": disposition}
