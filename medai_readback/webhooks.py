"""CALL-E webhook receiver — terminal call events for prescription readback.

CALL-E POSTs terminal events here instead of the caller polling. Events are
deduplicated on the CALL-E-Event-Id header and correlated back to a pending
confirmation through metadata.call_id.

metadata.call_id is the only reliable correlation key on the return path:
CALL-E's own call id is not known to your system when the result arrives, and
matching on phone number or timing breaks the moment two calls are in flight.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, Request
from loguru import logger

from medai_readback.confirmations import resolve_confirmation

router = APIRouter(prefix="/calle", tags=["calle"])

WEBHOOK_EVENTS_COLLECTION = "calle_webhook_events"

_TERMINAL_EVENTS = {"call.completed", "call.failed", "call.result_validation_failed"}

# Set by the application at startup (see app.py).
_db = None


def set_db(db) -> None:
    """Register the database handle the route handler should use."""
    global _db
    _db = db


async def handle_event(db, event_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Process one CALL-E terminal event. Idempotent on event_id."""
    event_type = payload.get("event", "")
    if event_type not in _TERMINAL_EVENTS:
        logger.info("Ignoring non-terminal CALL-E event: {}", event_type)
        return {"status": "ignored", "reason": f"unhandled event type {event_type}"}

    call_id = (payload.get("metadata") or {}).get("call_id")
    if not call_id:
        logger.warning("CALL-E event {} has no metadata.call_id", event_id)
        return {"status": "ignored", "reason": "missing metadata.call_id"}

    events = db.get_collection(WEBHOOK_EVENTS_COLLECTION)
    if await events.find_one({"event_id": event_id}):
        logger.info("Duplicate CALL-E event {}", event_id)
        return {"status": "duplicate"}

    await events.insert_one(
        {
            "event_id": event_id,
            "event": event_type,
            "call_id": call_id,
            "payload": payload,
            "received_at": datetime.now(timezone.utc),
        }
    )

    structured = (payload.get("structured_result") or {}) if event_type == "call.completed" else {}
    transcript = payload.get("transcript") or []
    disposition = await resolve_confirmation(db, call_id, structured, transcript)

    return {"status": "processed", "disposition": disposition}


@router.post("/webhook")
async def calle_webhook(
    request: Request,
    calle_event_id: Optional[str] = Header(default=None, alias="CALL-E-Event-Id"),
) -> Dict[str, Any]:
    """Receive a terminal call event from CALL-E."""
    payload = await request.json()
    event_id = calle_event_id or f"noheader-{datetime.now(timezone.utc).timestamp()}"
    return await handle_event(_db, event_id, payload)
