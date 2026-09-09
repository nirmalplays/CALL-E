"""Adherence check call — task prompt builder and result schema.

Ports the existing MedAI adherence-call outcome taxonomy onto CALL-E (PRD
Workstream B: "Port the adherence call result schema"). This is a separate
call type from the readback call in readback.py — it fires on the
platform's existing adherence schedule (SchedulerService, outside this
repo) once a regimen has already been confirmed, not automatically from
confirmations.py's on_confirmed hook. A real adherence call happens at the
medication's scheduled time, not the moment it's confirmed.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

ADHERENCE_OUTCOMES = ("taken", "already_taken", "not_taken", "refusing", "confused", "no_answer")

# taken/already_taken close the loop; everything else needs a caregiver
# (see escalation.py — this is the signal it escalates on).
ESCALATION_OUTCOMES: FrozenSet[str] = frozenset({"not_taken", "refusing", "confused", "no_answer"})


def build_adherence_task(patient_name: str, medication_name: str, dosage: str, slot: str) -> str:
    """Build the CALL-E task instruction for one scheduled adherence check."""
    if not medication_name.strip():
        raise ValueError("Adherence check requires a medication name.")

    greeting_name = patient_name.strip() or "there"
    slot_phrase = slot.strip().lower() or "today"

    return f"""You are a friendly voice assistant for MedAI, a medication adherence service.
You are calling {greeting_name} to check on one scheduled medication.

IMPORTANT SAFETY RULES — follow these strictly:
1. First confirm identity. Say: "Hello, this is MedAI calling for {greeting_name}. Am I speaking with them?"
   - If the person says no, or someone else answers, say: "No problem. Could you please ask them to call us back? Thank you." Then end the call.
   - If you reach voicemail, leave only: "This is MedAI. Please call us back at your convenience." Never leave medication details on voicemail.
2. Do NOT speak the medication name until identity is confirmed.

Once identity is confirmed, ask: "Did you take your {medication_name.strip()}, {dosage.strip()}, for {slot_phrase}?"

Listen for one of: already taken, taken just now, not taken, refusing to take it, or confused about
the question. If they say they have not taken it, refuse, or seem confused, gently ask why and record
their reason in their own words. Do not argue, persuade, or give medical advice — just record what
they say.
"""


ADHERENCE_RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["outcome"],
    "properties": {
        "outcome": {
            "type": "string",
            "enum": list(ADHERENCE_OUTCOMES),
            "description": "What the patient reported about this scheduled dose",
        },
        "reason": {
            "type": "string",
            "description": "Patient's own words, if they refused, skipped, or were confused",
        },
    },
}


def needs_escalation(outcome: str) -> bool:
    """Whether this adherence outcome should trigger a caregiver escalation call."""
    return outcome in ESCALATION_OUTCOMES
