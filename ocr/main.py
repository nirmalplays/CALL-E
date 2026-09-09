"""Fixture-backed OCR extraction — stands in for the real OCR service.

The production OCR service (PRD open question 1: what actually runs on
OCR_BASE_URL, :8081) isn't available in this repo. Until it's wired up, this
module returns pre-extracted, hand-checked medication data for known scan
ids, so the CALL-E readback path (medai_readback/readback.py) can run
standalone — for tests, dry-run demos, and the submission video. This is the
"fixture-based mode" risk mitigation from PRD section 11
("OCR service not reproducible by judges").

medai_readback/readback.py documents the medication dict shape it expects
as coming from "ocr/main.py::MedicationItem" — this module is that contract.
"""

from __future__ import annotations

from typing import List, TypedDict


class MedicationItem(TypedDict):
    name: str
    dosage: str
    quantity: str
    schedule: List[str]  # any of MORNING, AFTERNOON, EVENING
    duration: str
    instructions: str


class PrescriptionScan(TypedDict):
    patient_name: str
    medications: List[MedicationItem]


# Fixture scans, keyed by scan_id. Each stands in for one handwritten
# prescription already run through extraction.
_FIXTURES: dict[str, PrescriptionScan] = {
    "demo-clean": {
        "patient_name": "Ravi Kumar",
        "medications": [
            {
                "name": "Metformin",
                "dosage": "500mg",
                "quantity": "1",
                "schedule": ["MORNING", "EVENING"],
                "duration": "30 days",
                "instructions": "after food",
            },
            {
                "name": "Amoxicillin",
                "dosage": "250mg",
                "quantity": "1",
                "schedule": ["MORNING", "EVENING"],
                "duration": "5 days",
                "instructions": "after food",
            },
        ],
    },
    "demo-misread-dose": {
        "patient_name": "Lakshmi Nair",
        "medications": [
            # OCR read the doctor's "50mg" as "5mg" — the PRD's own example
            # of a silent dose misread (PRD section 2). Reading this back is
            # what gives the patient something real to correct on camera.
            {
                "name": "Metformin",
                "dosage": "5mg",
                "quantity": "1",
                "schedule": ["MORNING", "EVENING"],
                "duration": "30 days",
                "instructions": "after food",
            },
            {
                "name": "Paracetamol",
                "dosage": "650mg",
                "quantity": "1",
                "schedule": ["AFTERNOON"],
                "duration": "5 days",
                "instructions": "when in pain",
            },
        ],
    },
}


def extract_prescription(scan_id: str) -> PrescriptionScan:
    """Return the extracted patient name + medications for a scanned prescription.

    Stands in for a real call to the OCR service. Raises KeyError for an
    unknown scan_id — callers should treat that the same as an OCR failure
    and fall back to dashboard staff review, per the PRD Workstream A flow.
    """
    try:
        return _FIXTURES[scan_id]
    except KeyError:
        raise KeyError(f"No OCR fixture for scan_id={scan_id!r}") from None


def available_scan_ids() -> List[str]:
    return sorted(_FIXTURES)
