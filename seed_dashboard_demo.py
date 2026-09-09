"""Seed the demo store with realistic confirmations, then serve app.py's
FastAPI app in this same process so the seeded data and the HTTP server
share one in-memory store (see app.py's docstring for why that has to be
one process).

This simulates what a phone call's OUTCOME would be — the structured_result
CALL-E would hand back — rather than placing a real call: that needs a real
CALLE_API_KEY and a human to answer the phone, neither of which this script
has. Every other step (readback task building, pending-confirmation
storage, webhook resolution, outcome routing, dashboard rendering) runs the
actual production code in medai_readback/, unmocked.

Run:
    python seed_dashboard_demo.py
Then open:
    http://127.0.0.1:8123/dashboard
    http://127.0.0.1:8123/demo/confirmations   (raw JSON)
"""

from __future__ import annotations

import asyncio

import uvicorn

import app as app_module
from medai_readback.confirmations import create_pending_confirmation, resolve_confirmation
from ocr.main import extract_prescription


async def seed() -> None:
    db = app_module.db

    # 1) Corrected — OCR misread the dose, the patient catches it live.
    misread = extract_prescription("demo-misread-dose")
    call_id = await create_pending_confirmation(
        db, patient_id="demo-misread-dose", phone_number="+919876543210",
        patient_name=misread["patient_name"], age="58", gender="female",
        medications=misread["medications"], enrollment_days=30,
    )
    await resolve_confirmation(db, call_id, {
        "reached_patient": "yes", "overall": "corrected",
        "medications": [
            {"name_as_read": "Metformin", "status": "corrected",
             "correction_text": "it's actually 50 milligrams, not 5"},
            {"name_as_read": "Paracetamol", "status": "confirmed"},
        ],
        "patient_notes": "please call after 6pm next time",
    })

    # 2) Scheduled — everything confirmed as read.
    clean = extract_prescription("demo-clean")
    call_id = await create_pending_confirmation(
        db, patient_id="demo-clean", phone_number="+919812345678",
        patient_name=clean["patient_name"], age="61", gender="male",
        medications=clean["medications"], enrollment_days=30,
    )
    await resolve_confirmation(db, call_id, {
        "reached_patient": "yes", "overall": "confirmed",
        "medications": [
            {"name_as_read": "Metformin", "status": "confirmed"},
            {"name_as_read": "Amoxicillin", "status": "confirmed"},
        ],
    })

    # 3) Fallback — wrong person answered; no medication name was ever spoken.
    call_id = await create_pending_confirmation(
        db, patient_id="demo-wrong-person", phone_number="+919900011122",
        patient_name="Suresh Babu", age="70", gender="male",
        medications=[{"name": "Atorvastatin", "dosage": "10mg", "quantity": "1",
                      "schedule": ["EVENING"], "duration": "90 days", "instructions": "after dinner"}],
        enrollment_days=30,
    )
    await resolve_confirmation(db, call_id, {
        "reached_patient": "wrong_person", "overall": "unclear", "medications": [],
    })

    # 4) Still pending — call placed, outcome not in yet.
    await create_pending_confirmation(
        db, patient_id="demo-pending", phone_number="+919845567788",
        patient_name="Fatima Sheikh", age="45", gender="female",
        medications=[{"name": "Losartan", "dosage": "25mg", "quantity": "1",
                      "schedule": ["MORNING"], "duration": "30 days", "instructions": "after food"}],
        enrollment_days=30,
    )


def main() -> None:
    asyncio.run(seed())
    print("Seeded 4 confirmations. Serving on http://127.0.0.1:8123")
    print("  /dashboard            human-readable queue")
    print("  /demo/confirmations   raw JSON")
    uvicorn.run(app_module.app, host="127.0.0.1", port=8123, log_level="warning")


if __name__ == "__main__":
    main()
