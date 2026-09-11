"""Voice prescription readback — task prompt builder and result schema.

Builds the CALL-E task instruction that reads an OCR-extracted prescription
back to the patient and captures a per-medication confirmation.

Medication dicts use the OCR service shape (see ocr/main.py::MedicationItem):
    {name, dosage, quantity, schedule: [MORNING|AFTERNOON|EVENING],
     duration, instructions}

Safety rules encoded in the prompt (PRD S2, A5, A6):
  - identity is confirmed before any medication name is spoken
  - no medication details are left on voicemail
  - corrections are explicitly described to the patient as staff-reviewed
"""

from __future__ import annotations

from typing import Any, Dict, List

# A call reading more than this many medications is too long to be reliable.
# Overflow is routed to dashboard staff review instead.
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
    """Render one medication as a single spoken sentence."""
    name = med.get("name", "").strip() or "unnamed medication"
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
    """Build the CALL-E task instruction for a prescription readback call."""
    if not medications:
        raise ValueError("Readback requires at least one medication.")
    if exceeds_readback_cap(medications):
        raise ValueError(
            f"Medication count {len(medications)} exceeds readback cap "
            f"of {MAX_READBACK_MEDICATIONS}; route to staff review."
        )

    readback_text = "\n".join(
        format_medication_line(i, m) for i, m in enumerate(medications, 1)
    )
    greeting_name = patient_name.strip() or "there"

    return f"""You are a friendly voice assistant for MedAI, a medication adherence service.
You are calling a patient to confirm a prescription that was scanned from a handwritten note.

IMPORTANT SAFETY RULES — follow these strictly:
1. First confirm identity. Say: "Hello, this is MedAI calling for {greeting_name}. Am I speaking with the patient who visited the doctor?"
   - If the person says no, or someone else answers, say: "No problem. Could you please ask them to call us back? Thank you." Then end the call.
   - If you reach voicemail, leave only: "This is MedAI. Please call us back at your convenience." Never leave medication details on voicemail.
2. Do NOT speak any medication names until identity is confirmed.

Once identity is confirmed, say:
"Thank you. We scanned your prescription and want to read it back to make sure we got it right. I will read each medicine one by one. Please tell me if it is correct, or what needs to change."

Then read back EACH medication ONE BY ONE. After each one, ask "Is this correct, or would you like to make any changes?" and wait for the answer before moving to the next.

{readback_text}

After all medications have been reviewed:
- If everything was confirmed: "Thank you for confirming. Your confirmation has been recorded for the care team. Have a good day!"
- If anything was corrected: "Thank you, I have noted that. Our team will review your corrections before updating your records — nothing changes without staff verification. Have a good day!"

Record for each medication whether the patient confirmed it, corrected it, or was unsure, and capture any correction in the patient's own words.
"""


READBACK_RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["reached_patient", "overall", "medications"],
    "properties": {
        "reached_patient": {
            "type": "string",
            "enum": ["yes", "no", "wrong_person"],
            "description": "Whether the actual patient was reached on this call",
        },
        "overall": {
            "type": "string",
            "enum": ["confirmed", "corrected", "unclear", "refused"],
            "description": (
                "confirmed = every medication confirmed; "
                "corrected = at least one correction; "
                "unclear = patient could not confirm; "
                "refused = patient declined to continue"
            ),
        },
        "medications": {
            "type": "array",
            "description": "One entry per medication read to the patient",
            "items": {
                "type": "object",
                "required": ["name_as_read", "status"],
                "properties": {
                    "name_as_read": {
                        "type": "string",
                        "description": "Medication name as read to the patient",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["confirmed", "corrected", "unsure"],
                    },
                    "correction_text": {
                        "type": "string",
                        "description": "Patient's correction, verbatim, if any",
                    },
                },
            },
        },
        "patient_notes": {
            "type": "string",
            "description": "Any other comment the patient made",
        },
    },
}
