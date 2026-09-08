"""
MedAI - Voice Prescription Readback Test Call
==============================================
Uses the CALL-E Python SDK (`calle-ai` on PyPI, imports as `calle`) to place
an outbound call with hardcoded dummy medication data. The voice agent reads
back each medication and captures a structured per-medication confirmation
from the patient.

Setup:
    pip install -r requirements.txt
    cp .env.example .env   # fill in CALLE_API_KEY and TEST_PHONE

Usage:
    python test_readback_call.py            # places a real call
    python test_readback_call.py --dry-run  # builds + prints the payload only
"""

import argparse
import json
import sys

import env_config as cfg

# -- Hardcoded dummy prescription (stands in for Nikhil's OCR output) ----
MEDICATIONS = [
    {"name": "Metformin",    "dose": "500 mg", "frequency": "Once daily",  "timing": "After dinner",                    "duration": "30 days"},
    {"name": "Paracetamol",  "dose": "650 mg", "frequency": "SOS",         "timing": "When you have fever or pain",     "duration": "As needed"},
    {"name": "Amoxicillin",  "dose": "250 mg", "frequency": "Twice daily", "timing": "After breakfast and after dinner", "duration": "5 days"},
]


# -- Build the readback prompt --------------------------------------------
def build_task_prompt(medications):
    med_lines = [
        f"Medication {i}: {m['name']} {m['dose']}, "
        f"to be taken {m['frequency'].lower()}, {m['timing'].lower()}, "
        f"for {m['duration']}."
        for i, m in enumerate(medications, 1)
    ]
    readback_text = "\n".join(med_lines)

    return f"""You are a friendly voice assistant for MedAI, a medication adherence platform.
You are calling a patient to confirm a prescription that was scanned from a handwritten note.

IMPORTANT SAFETY RULES (follow these strictly):
1. First, confirm the patient's identity. Say: "Hello, this is MedAI calling. Am I speaking with the patient who visited the doctor today?"
   - If the person says no or someone else answers, say: "Could you please have the patient call us back? Thank you." and end the call.
   - Never leave medication details on voicemail.
2. Do NOT speak any medication names until identity is confirmed.

Once identity is confirmed, say:
"Great! We scanned your prescription and want to read it back to make sure everything is correct. I will read each medicine one by one. Please tell me if it is correct, or let me know what needs to be changed."

Then read back EACH medication ONE BY ONE and wait for the patient's response after each:

{readback_text}

After reading each medication, ask: "Is this correct, or would you like to make any changes?"

After all medications are reviewed:
- If everything was confirmed, say: "Thank you for confirming all your medications. We will now set up your medication reminders. Have a great day!"
- If any medication was corrected, say: "I have noted your corrections. Our team will review them before updating your records. Nothing will be changed without staff verification. Have a great day!"
"""


# -- Result schema (matches PRD Section 6, Workstream A) ------------------
RESULT_SCHEMA = {
    "type": "object",
    "required": ["reached_patient", "overall", "medications"],
    "properties": {
        "reached_patient": {
            "type": "string",
            "enum": ["yes", "no", "wrong_person"],
            "description": "Whether the actual patient was reached on the call",
        },
        "overall": {
            "type": "string",
            "enum": ["confirmed", "corrected", "unclear", "refused"],
            "description": "Overall outcome of the prescription readback",
        },
        "medications": {
            "type": "array",
            "description": "Per-medication confirmation status",
            "items": {
                "type": "object",
                "required": ["name_as_read", "status"],
                "properties": {
                    "name_as_read": {
                        "type": "string",
                        "description": "The medication name as it was read to the patient",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["confirmed", "corrected", "unsure"],
                        "description": "Whether the patient confirmed, corrected, or was unsure about this medication",
                    },
                    "correction_text": {
                        "type": "string",
                        "description": "Verbatim correction from the patient, if any",
                    },
                },
            },
        },
        "patient_notes": {
            "type": "string",
            "description": "Any additional notes or comments from the patient",
        },
    },
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build the task prompt + payload and print them without placing a call.",
    )
    args = parser.parse_args()

    task_prompt = build_task_prompt(MEDICATIONS)

    print("=" * 60)
    print("  MedAI - Voice Prescription Readback Test Call")
    print("=" * 60)
    print(f"\n[MEDS]   Medications   : {len(MEDICATIONS)}")
    for m in MEDICATIONS:
        print(f"    - {m['name']} {m['dose']} - {m['frequency']} ({m['timing']})")

    if args.dry_run:
        print("\n[DRY RUN] No call will be placed. Payload that would be sent:\n")
        payload = {
            "task": task_prompt,
            "recipient": {
                "phones": [cfg.TEST_PHONE or "<TEST_PHONE not set>"],
                "region": cfg.TEST_REGION,
                "locale": cfg.TEST_LOCALE,
            },
            "result_schema": RESULT_SCHEMA,
        }
        print(json.dumps(payload, indent=2))
        return

    api_key = cfg.require("CALLE_API_KEY", cfg.API_KEY)
    phone = cfg.require("TEST_PHONE", cfg.TEST_PHONE)

    print(f"\n[PHONE]  Target phone  : {phone}")
    print(f"[KEY]    API key       : {api_key[:16]}...{api_key[-4:]}")
    print("-" * 60)

    from calle import CalleClient  # deferred: only needed for a real call

    client = CalleClient(api_key=api_key, base_url=cfg.BASE_URL)

    print("\n[WAIT]  Creating call and waiting for completion...")
    print("        (Your phone should ring shortly. Pick up and interact!)\n")

    try:
        call = client.calls.create_and_wait(
            task=task_prompt,
            recipient={"phones": [phone], "region": cfg.TEST_REGION, "locale": cfg.TEST_LOCALE},
            result_schema=RESULT_SCHEMA,
        )
    except Exception as e:
        print(f"\n[ERROR]  Call failed with error: {e}")
        sys.exit(1)

    # -- Print results -----------------------------------------------------
    print("\n" + "=" * 60)
    print("  CALL RESULTS")
    print("=" * 60)
    print(f"\n[STATUS]      : {call.get('status')}")
    print(f"[COMPLETED]   : {call.get('task_completed')}")
    print(f"[CONFIDENCE]  : {call.get('completion_confidence')}")

    structured = call.get("structured_result")
    print("\n[RESULT]      :")
    print(json.dumps(structured, indent=2) if structured else "    (none)")

    evidence = call.get("evidence")
    print("\n[EVIDENCE]    :")
    if evidence:
        for e in evidence:
            print(f"    - {e}")
    else:
        print("    (none)")

    transcript = call.get("transcript") or call.get("transcript_turns")
    if transcript:
        print("\n[TRANSCRIPT]  :")
        for turn in transcript:
            print(f"    [{turn.get('speaker', '?')}] {turn.get('text', '')}")

    print("\n[RAW RESPONSE]:")
    print(json.dumps(call, indent=2, default=str))

    print("\n" + "=" * 60)
    print("  END OF TEST")
    print("=" * 60)


if __name__ == "__main__":
    main()
