import pytest

from readback_task import (
    MAX_READBACK_MEDICATIONS,
    READBACK_RESULT_SCHEMA,
    build_readback_task,
    exceeds_readback_cap,
    format_medication_line,
)

MEDS = [
    {
        "name": "Metformin",
        "dosage": "500mg",
        "quantity": "1",
        "schedule": ["MORNING", "EVENING"],
        "duration": "30 days",
        "instructions": "after food",
    },
]


def test_format_medication_line_reads_naturally():
    line = format_medication_line(1, MEDS[0])
    assert "Metformin" in line
    assert "morning and evening" in line


def test_identity_check_precedes_item_name():
    task = build_readback_task("Demo Patient", MEDS)
    assert task.index("Am I speaking with") < task.index("Metformin")


def test_voicemail_never_gets_item_details():
    task = build_readback_task("Demo Patient", MEDS)
    assert "voicemail" in task.lower()
    assert "Never leave the record's details on voicemail" in task


def test_corrections_are_described_as_staff_reviewed():
    task = build_readback_task("Demo Patient", MEDS)
    assert "without staff verification" in task


def test_empty_medications_rejected():
    with pytest.raises(ValueError, match="at least one item"):
        build_readback_task("Demo Patient", [])


def test_overflow_routes_to_cap_error():
    too_many = [MEDS[0]] * (MAX_READBACK_MEDICATIONS + 1)
    assert exceeds_readback_cap(too_many)
    with pytest.raises(ValueError, match="exceeds readback cap"):
        build_readback_task("Demo Patient", too_many)


def test_result_schema_has_no_free_text_status():
    item = READBACK_RESULT_SCHEMA["properties"]["medications"]["items"]["properties"]
    assert item["status"]["enum"] == ["confirmed", "corrected", "unsure"]
