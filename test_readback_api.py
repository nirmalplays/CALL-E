"""
MedAI - Readback Test Call (REST API)
======================================
Uses the CALL-E REST API directly (no SDK dependency) with explicit
region=IN routing. This historical script is now an offline fixture preview only.

Setup:
    pip install httpx
    cp .env.example .env   # fill in CALLE_API_KEY and TEST_PHONE

Usage:
    python test_readback_api.py            # offline fixture preview
    python test_readback_api.py --dry-run  # builds + prints the payload only
"""

import argparse
import json
import sys
import time

import httpx

import env_config as cfg

TASK_PROMPT = """You are a friendly voice assistant for MedAI, a medication adherence platform.
You are calling to confirm a prescription that was scanned from a handwritten note.

SAFETY RULES:
1. First confirm identity: "Hello, this is MedAI calling. Am I speaking with the patient who visited the doctor today?"
   - If no or wrong person: "Could you please have the patient call us back? Thank you." Then end the call.
   - Never leave medication details on voicemail.
2. Do NOT speak medication names until identity is confirmed.

Once confirmed, say: "We scanned your prescription and want to read it back to you. I will read each medicine one by one. Please tell me if it is correct or if something needs to change."

Read back each medication and wait for response:

Medication 1: Metformin 500 milligrams, once daily, after dinner, for 30 days.
Medication 2: Paracetamol 650 milligrams, as needed when you have fever or pain.
Medication 3: Amoxicillin 250 milligrams, twice daily, after breakfast and after dinner, for 5 days.

After each one ask: "Is this correct, or would you like to make any changes?"

After all reviewed:
- All confirmed: "Thank you for confirming. We will set up your medication reminders. Have a great day!"
- Any corrected: "I have noted your corrections. Our team will review them before updating. Have a great day!"
"""

RESULT_SCHEMA = {
    "type": "object",
    "required": ["reached_patient", "overall", "medications"],
    "properties": {
        "reached_patient": {"type": "string", "enum": ["yes", "no", "wrong_person"]},
        "overall": {"type": "string", "enum": ["confirmed", "corrected", "unclear", "refused"]},
        "medications": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name_as_read", "status"],
                "properties": {
                    "name_as_read": {"type": "string"},
                    "status": {"type": "string", "enum": ["confirmed", "corrected", "unsure"]},
                    "correction_text": {"type": "string"},
                },
            },
        },
        "patient_notes": {"type": "string"},
    },
}


def build_payload(phone, region, locale):
    return {
        "task": TASK_PROMPT,
        "recipients": [{"phones": [phone], "region": region, "locale": locale}],
        "result_schema": RESULT_SCHEMA,
    }


def main():
    parser = argparse.ArgumentParser(description="Legacy fixture preview only. Use the authenticated dashboard for real calls.")
    parser.add_argument('--dry-run', action='store_true', help='Preview only (also the default).')
    parser.parse_args()
    print('OFFLINE FIXTURE PREVIEW: no API requests or phone calls.')
    print(json.dumps(build_payload('<RECIPIENT>', cfg.TEST_REGION, cfg.TEST_LOCALE), indent=2))


if __name__ == '__main__':
    main()
