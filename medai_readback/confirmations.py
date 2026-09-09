"""Pending prescription confirmations — store and outcome routing.

A readback call is recorded here before it is placed. When CALL-E returns a
structured result, resolve_confirmation() routes it:

    confirmed  -> invoke the registered on_confirmed hook
    corrected  -> staff review task, nothing scheduled
    otherwise  -> fallback to human review, nothing scheduled

Safety: nothing is handed downstream unless the patient was actually reached
AND confirmed every medication. Corrections are stored verbatim for a human;
they are never written back to the prescription record here.

The downstream action is injected rather than imported, so this module has no
dependency on any particular scheduling system. Register yours with
set_on_confirmed(); the default is a no-op that only logs.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from loguru import logger

CONFIRMATIONS_COLLECTION = "pending_confirmations"

# Signature: async (confirmation_doc: dict) -> None
OnConfirmed = Callable[[Dict[str, Any]], Awaitable[None]]


async def _default_on_confirmed(doc: Dict[str, Any]) -> None:
    logger.info(
        "Confirmed regimen for {} ({} medications) — no scheduler registered; "
        "call set_on_confirmed() to hook your scheduling system.",
        doc.get("patient_name", "?"),
        len(doc.get("medications", [])),
    )


_on_confirmed: OnConfirmed = _default_on_confirmed


def set_on_confirmed(hook: OnConfirmed) -> None:
    """Register the action to run when a patient confirms their prescription."""
    global _on_confirmed
    _on_confirmed = hook


def build_confirmation_call_id(patient_id: str) -> str:
    """Deterministic per patient per day, so a re-scan does not double-call."""
    return f"{patient_id}-{date.today().isoformat()}-readback"


async def create_pending_confirmation(
    db,
    *,
    patient_id: str,
    phone_number: str,
    patient_name: str,
    age: str,
    gender: str,
    medications: List[Dict[str, Any]],
    enrollment_days: int,
) -> str:
    """Record a readback call as pending and return its call_id."""
    call_id = build_confirmation_call_id(patient_id)
    col = db.get_collection(CONFIRMATIONS_COLLECTION)

    existing = await col.find_one({"call_id": call_id})
    if existing:
        logger.info("Pending confirmation already exists for {}", call_id)
        return call_id

    await col.insert_one(
        {
            "call_id": call_id,
            "patient_id": patient_id,
            "phone_number": phone_number,
            "patient_name": patient_name,
            "age": age,
            "gender": gender,
            "medications": medications,
            "enrollment_days": enrollment_days,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
        }
    )
    logger.info("Created pending confirmation {}", call_id)
    return call_id


def _extract_corrections(structured: Dict[str, Any]) -> List[Dict[str, str]]:
    out = []
    for m in structured.get("medications", []) or []:
        if m.get("status") in ("corrected", "unsure"):
            out.append(
                {
                    "name_as_read": m.get("name_as_read", ""),
                    "status": m.get("status", ""),
                    "correction_text": m.get("correction_text", "") or "",
                }
            )
    return out


def decide(structured: Dict[str, Any]) -> str:
    """Map a structured readback result onto a disposition.

    Handing anything downstream requires BOTH that the patient was reached and
    that the overall outcome is 'confirmed'. Any other combination falls back
    to human review — including a model that returns 'confirmed' while
    reporting it never reached the patient.
    """
    reached = structured.get("reached_patient")
    overall = structured.get("overall")

    if reached != "yes":
        return "fallback"
    if overall == "confirmed":
        return "scheduled"
    if overall == "corrected":
        return "review"
    return "fallback"


async def resolve_confirmation(
    db,
    call_id: str,
    structured_result: Dict[str, Any],
    transcript: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Route a returned readback result. Idempotent on call_id."""
    col = db.get_collection(CONFIRMATIONS_COLLECTION)
    doc = await col.find_one({"call_id": call_id})
    if not doc:
        logger.warning("No pending confirmation for call_id={}", call_id)
        return "unknown"

    if doc.get("status") != "pending":
        logger.info("Confirmation {} already resolved as {}", call_id, doc["status"])
        return doc["status"]

    disposition = decide(structured_result)
    corrections = _extract_corrections(structured_result)

    await col.update_one(
        {"call_id": call_id},
        {
            "$set": {
                "status": disposition,
                "structured_result": structured_result,
                "corrections": corrections,
                "transcript": transcript or [],
                "resolved_at": datetime.now(timezone.utc),
            }
        },
    )

    if disposition == "scheduled":
        await _on_confirmed(doc)

    logger.info("Confirmation {} resolved: {}", call_id, disposition)
    return disposition
