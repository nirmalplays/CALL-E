"""Readback task prompt builder and result schema.

No framework or database dependency — pure functions, safe to import
anywhere. See ../references/safety.md for why each rule below exists.

Item shape used in this example (adapt the fields to your own record):
    {name, dosage, quantity, schedule: [MORNING|AFTERNOON|EVENING],
     duration, instructions}
"""

from __future__ import annotations

from typing import Any, Dict, List

# A call reading more than this many items is too long to be reliable.
# Overflow routes to a human instead of attempting a degraded call.
MAX_READBACK_MEDICATIONS = 6

_SLOT_WORDS = {
    "MORNING": "morning",
    "AFTERNOON": "afternoon",
    "EVENING": "evening",
}


def _schedule_phrase(schedule: List[str]) -> str:
    """Render ['MORNING', 'EVENING'] as 'morning and evening'."""
    words = [_SLOT_WORDS.get(s.upper(), s.lower()) for s in schedule if s]
    if not words:
        return "as directed"
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " and " + words[-1]


def format_medication_line(index: int, med: Dict[str, Any]) -> str:
    """Render one item as a single spoken sentence."""
    name = med.get("name", "").strip() or "unnamed item"
    dosage = med.get("dosage", "").strip()
    quantity = str(med.get("quantity", "") or "").strip()
    duration = med.get("duration", "").strip()
    instructions = med.get("instructions", "").strip()

    parts = [f"Medication {index}: {name}"]
    if dosage:
        parts.append(dosage)

    schedule = _schedule_phrase(med.get("schedule", []))
    if quantity:
        parts.append(f"quantity {quantity}; timing {schedule}")
    else:
        parts.append(f"timing {schedule}")

    if duration:
        parts.append(f"for {duration}")
    if instructions:
        parts.append(instructions)

    return ", ".join(parts) + "."


def exceeds_readback_cap(medications: List[Dict[str, Any]]) -> bool:
    return len(medications) > MAX_READBACK_MEDICATIONS


def build_readback_task(patient_name: str, medications: List[Dict[str, Any]]) -> str:
    """Build the CALL-E task instruction for a record readback call."""
    if not medications:
        raise ValueError("Readback requires at least one item.")
    if exceeds_readback_cap(medications):
        raise ValueError(
            f"Item count {len(medications)} exceeds readback cap "
            f"of {MAX_READBACK_MEDICATIONS}; route to human review."
        )

    readback_text = "\n".join(
        format_medication_line(i, m) for i, m in enumerate(medications, 1)
    )
    greeting_name = patient_name.strip() or "there"

    return f"""You are a friendly voice assistant confirming a record with someone.
You are calling {greeting_name} to confirm a record extracted from an unreliable source.

IMPORTANT SAFETY RULES — follow these strictly:
1. First confirm identity. Say: "Hello, this is calling for {greeting_name}. Am I speaking with them?"
   - If the person says no, or someone else answers, say: "No problem. Could you please ask them to call us back? Thank you." Then end the call.
   - If you reach voicemail, leave only a generic callback request. Never leave the record's details on voicemail.
2. Do NOT speak any item details until identity is confirmed.

Once identity is confirmed, say:
"Thank you. We want to read back what we have on file to make sure we got it right. I will read each item one by one. Please tell me if it is correct, or what needs to change."

Then read back EACH item ONE BY ONE. After each one, ask "Is this correct, or would you like to make any changes?" and wait for the answer before moving to the next.

{readback_text}

After all items have been reviewed:
- If everything was confirmed: "Thank you for confirming. Have a good day!"
- If anything was corrected: "Thank you, I have noted that. Our team will review your corrections before updating anything — nothing changes without staff verification. Have a good day!"

Record for each item whether the person confirmed it, corrected it, or was unsure, and capture any correction in their own words.
"""


READBACK_RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["reached_patient", "overall", "medications"],
    "properties": {
        "reached_patient": {
            "type": "string",
            "enum": ["yes", "no", "wrong_person"],
            "description": "Whether the actual person was reached on this call",
        },
        "overall": {
            "type": "string",
            "enum": ["confirmed", "corrected", "unclear", "refused"],
            "description": (
                "confirmed = every item confirmed; "
                "corrected = at least one correction; "
                "unclear = could not confirm; "
                "refused = declined to continue"
            ),
        },
        "medications": {
            "type": "array",
            "description": "One entry per item read back",
            "items": {
                "type": "object",
                "required": ["name_as_read", "status"],
                "properties": {
                    "name_as_read": {
                        "type": "string",
                        "description": "Item name as read to the person",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["confirmed", "corrected", "unsure"],
                    },
                    "correction_text": {
                        "type": "string",
                        "description": "Correction, verbatim, if any",
                    },
                },
            },
        },
        "patient_notes": {
            "type": "string",
            "description": "Any other comment the person made",
        },
    },
}
