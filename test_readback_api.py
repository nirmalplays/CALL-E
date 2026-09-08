"""
MedAI - Readback Test Call (REST API)
======================================
Uses the CALL-E REST API directly (no SDK dependency) with explicit
region=IN routing. This is the script that placed the working self-test
call.

Setup:
    pip install httpx
    cp .env.example .env   # fill in CALLE_API_KEY and TEST_PHONE

Usage:
    python test_readback_api.py            # places a real call
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build + print the payload without calling the API.",
    )
    args = parser.parse_args()

    phone = cfg.TEST_PHONE if args.dry_run else cfg.require("TEST_PHONE", cfg.TEST_PHONE)
    payload = build_payload(phone or "<TEST_PHONE not set>", cfg.TEST_REGION, cfg.TEST_LOCALE)

    print("=" * 60)
    print("  MedAI - Readback Test Call (REST API)")
    print("=" * 60)
    print(f"\n[PHONE]   : {phone}")
    print(f"[REGION]  : {cfg.TEST_REGION}")
    print(f"[LOCALE]  : {cfg.TEST_LOCALE}")
    print("-" * 60)

    if args.dry_run:
        print("\n[DRY RUN] No call will be placed. Payload that would be sent:\n")
        print(json.dumps(payload, indent=2))
        return

    api_key = cfg.require("CALLE_API_KEY", cfg.API_KEY)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": f"medai-readback-test-{int(time.time())}",
    }

    # Step 1: Create the call
    print("\n[1/3] Creating call task...")
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{cfg.BASE_URL}/v1/calls", headers=headers, json=payload)

    if resp.status_code not in (200, 201, 202):
        print(f"[ERROR] API returned {resp.status_code}: {resp.text}")
        sys.exit(1)

    call_data = resp.json()
    call_id = call_data.get("id")
    print(f"[OK]    Call created: {call_id}")
    print(f"[INFO]  Status: {call_data.get('status')}")
    print("\n>>> YOUR PHONE SHOULD RING NOW - PICK UP! <<<\n")

    # Step 2: Poll for completion
    print("[2/3] Polling for call completion...")
    print("      (waiting 60s before first poll, then every 10s)\n")
    time.sleep(60)

    terminal_statuses = {"completed", "failed", "cancelled", "expired"}
    max_polls = 30
    poll_interval = 10

    for i in range(max_polls):
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{cfg.BASE_URL}/v1/calls/{call_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )

        if resp.status_code != 200:
            print(f"  Poll {i + 1}: HTTP {resp.status_code} - {resp.text[:100]}")
            time.sleep(poll_interval)
            continue

        result = resp.json()
        status = result.get("status", "unknown")
        print(f"  Poll {i + 1}: status={status}")

        if status in terminal_statuses:
            print(f"\n[3/3] Call reached terminal state: {status}")
            print("\n" + "=" * 60)
            print("  CALL RESULTS")
            print("=" * 60)
            print(f"\n[STATUS]      : {result.get('status')}")
            print(f"[COMPLETED]   : {result.get('task_completed')}")
            print(f"[CONFIDENCE]  : {result.get('completion_confidence')}")
            print(f"[SUMMARY]     : {result.get('summary')}")

            sr = result.get("structured_result")
            if sr:
                print("\n[STRUCTURED RESULT]:")
                print(json.dumps(sr, indent=2))

            evidence = result.get("evidence")
            if evidence:
                print("\n[EVIDENCE]:")
                for e in evidence:
                    print(f"  - {e}")

            recipients = result.get("recipients", [])
            for r in recipients:
                for attempt in r.get("attempts", []):
                    turns = attempt.get("transcript_turns", [])
                    if turns:
                        print("\n[TRANSCRIPT]:")
                        for t in turns:
                            print(f"  [{t.get('speaker', '?')}] {t.get('text', '')}")
                    failure = attempt.get("failure_code")
                    if failure:
                        print(f"\n[FAILURE]     : code={failure}, msg={attempt.get('failure_message')}")

            print("\n[RAW RESPONSE]:")
            print(json.dumps(result, indent=2, default=str))
            break

        time.sleep(poll_interval)
    else:
        print("\n[TIMEOUT] Call did not reach terminal state after polling.")

    print("\n" + "=" * 60)
    print("  END OF TEST")
    print("=" * 60)


if __name__ == "__main__":
    main()
