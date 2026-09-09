import pytest

from ocr.main import available_scan_ids, extract_prescription
from medai_readback.readback import build_readback_task, format_medication_line


def test_available_scan_ids_lists_all_fixtures():
    ids = available_scan_ids()
    assert "demo-clean" in ids
    assert "demo-misread-dose" in ids
    assert ids == sorted(ids)


def test_extract_prescription_returns_patient_and_medications():
    scan = extract_prescription("demo-clean")
    assert scan["patient_name"] == "Ravi Kumar"
    assert len(scan["medications"]) == 2
    assert scan["medications"][0]["name"] == "Metformin"


def test_extract_prescription_unknown_scan_id_raises():
    with pytest.raises(KeyError, match="demo-does-not-exist"):
        extract_prescription("demo-does-not-exist")


@pytest.mark.parametrize("scan_id", ["demo-clean", "demo-misread-dose"])
def test_every_fixture_matches_the_medication_item_shape(scan_id):
    """readback.py documents this exact shape — a fixture drifting from it
    would fail silently as a blank line on the call instead of a test."""
    scan = extract_prescription(scan_id)
    required_keys = {"name", "dosage", "quantity", "schedule", "duration", "instructions"}
    for med in scan["medications"]:
        assert required_keys.issubset(med.keys())
        assert isinstance(med["schedule"], list)
        assert all(slot in ("MORNING", "AFTERNOON", "EVENING") for slot in med["schedule"])


@pytest.mark.parametrize("scan_id", ["demo-clean", "demo-misread-dose"])
def test_every_fixture_builds_a_valid_readback_task(scan_id):
    """The real integration check: fixture output must actually flow through
    build_readback_task without tripping the cap or the empty-medications guard."""
    scan = extract_prescription(scan_id)
    task = build_readback_task(scan["patient_name"], scan["medications"])
    for med in scan["medications"]:
        assert med["name"] in task


def test_misread_dose_fixture_reads_back_the_ocr_error_verbatim():
    """This fixture exists to give the demo something to correct on camera —
    the readback line has to actually say the wrong dose CALL-E extracted,
    not the correct one, or there's nothing for the patient to catch."""
    scan = extract_prescription("demo-misread-dose")
    metformin = next(m for m in scan["medications"] if m["name"] == "Metformin")
    assert metformin["dosage"] == "5mg"
    line = format_medication_line(1, metformin)
    assert "5mg" in line
