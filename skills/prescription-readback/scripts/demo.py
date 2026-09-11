"""Runs the readback pattern end to end with fake data.

No network call, no real phone number — safe to run anywhere.

    python demo.py
"""

from __future__ import annotations

from outcome_routing import decide
from readback_task import build_readback_task

MASKED_PHONE = "+91••••••210"  # never a real number in this demo

MEDICATIONS = [
    {
        "name": "Metformin",
        "dosage": "500mg",
        "quantity": "1",
        "schedule": ["MORNING", "EVENING"],
        "duration": "30 days",
        "instructions": "after food",
    },
]


def main() -> None:
    task = build_readback_task("Demo Patient", MEDICATIONS)
    print(f"Would call {MASKED_PHONE} with task:\n")
    print(task)

    # Simulate a CALL-E result instead of placing a real call.
    fake_result = {
        "reached_patient": "yes",
        "overall": "confirmed",
        "medications": [{"name_as_read": "Metformin", "status": "confirmed"}],
    }
    print(f"\nSimulated result: {fake_result}")
    print(f"Disposition: {decide(fake_result, MEDICATIONS)}")


if __name__ == "__main__":
    main()
