"""Caregiver escalation call — reuses the adherence call's failure signal.

PRD Workstream B: "Escalation call reuses the existing escalation trigger;
recipients[] carries the caregiver number with context from the failed
patient call." This module only builds the task for that caregiver call —
deciding WHEN to escalate is medai_readback.adherence.needs_escalation().
"""

from __future__ import annotations

from typing import Any, Dict

_REASON_PHRASES = {
    "not_taken": "did not take",
    "refusing": "declined to take",
    "confused": "was unsure about",
    "no_answer": "could not be reached about",
}


def build_escalation_task(
    caregiver_name: str,
    patient_name: str,
    medication_name: str,
    patient_outcome: str,
    patient_reason: str = "",
) -> str:
    """Build the CALL-E task instruction for a caregiver escalation call."""
    if not caregiver_name.strip():
        raise ValueError("Escalation requires a caregiver name.")
    if not patient_name.strip():
        raise ValueError("Escalation requires the patient's name.")

    caregiver = caregiver_name.strip()
    patient = patient_name.strip()
    phrase = _REASON_PHRASES.get(patient_outcome, "had an issue with")
    reason_line = f' They told us: "{patient_reason.strip()}"' if patient_reason.strip() else ""

    return f"""You are a friendly voice assistant for MedAI, a medication adherence service.
You are calling {caregiver}, the registered caregiver for {patient}.

First confirm identity. Say: "Hello, this is MedAI calling for {caregiver}. Am I speaking with them?"
If the answerer is not the registered caregiver or identity is uncertain, ask them
to have the caregiver contact the care team and end the call. Do not disclose
the patient's name, medication, or reason for the call before identity is confirmed.
If you reach voicemail, leave only: "This is MedAI. Please contact our care team."
Never leave patient or medication details on voicemail.

Only after the registered caregiver confirms identity, say: "Hello, this is MedAI calling about {patient}'s medication, {medication_name.strip()}.
We wanted to let you know that {patient} {phrase} this dose.{reason_line} Could you please
check in with them?"

Do not give medical advice. If the caregiver has questions you cannot answer, tell them our
care team will follow up, and end the call politely.
"""


ESCALATION_RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["reached_caregiver"],
    "properties": {
        "reached_caregiver": {
            "type": "string",
            "enum": ["yes", "no"],
            "description": "Whether the caregiver was reached on this call",
        },
        "caregiver_notes": {
            "type": "string",
            "description": "Anything the caregiver said worth passing to staff",
        },
    },
}
