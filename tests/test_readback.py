import pytest

from medai_readback.readback import (
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
    {
        "name": "Amoxicillin",
        "dosage": "250mg",
        "quantity": "1",
        "schedule": ["MORNING"],
        "duration": "5 days",
        "instructions": "",
    },
]


def test_format_medication_line_reads_naturally():
    line = format_medication_line(1, MEDS[0])
    assert "Medication 1" in line
    assert "Metformin" in line
    assert "500mg" in line
    assert "morning and evening" in line
    assert "30 days" in line
    assert "after food" in line


def test_format_medication_line_omits_empty_instructions():
    line = format_medication_line(2, MEDS[1])
    assert "Amoxicillin" in line
    assert "morning" in line
    assert line.rstrip().endswith(".")


def test_build_task_includes_identity_check_before_medications():
    task = build_readback_task("Ravi Kumar", MEDS)
    identity_pos = task.index("Am I speaking with")
    med_pos = task.index("Metformin")
    assert identity_pos < med_pos, "identity check must precede any medication name"


def test_build_task_forbids_voicemail_and_third_party_disclosure():
    task = build_readback_task("Ravi Kumar", MEDS)
    assert "voicemail" in task.lower()
    assert "Do NOT speak any medication names until identity is confirmed" in task


def test_build_task_states_corrections_are_not_auto_applied():
    task = build_readback_task("Ravi Kumar", MEDS)
    assert "review" in task.lower()
    assert "without staff verification" in task or "before updating" in task


def test_build_task_asks_after_each_medication():
    task = build_readback_task("Ravi Kumar", MEDS)
    assert "one by one" in task.lower()
    assert "Is this correct" in task


def test_build_task_includes_every_medication():
    task = build_readback_task("Ravi Kumar", MEDS)
    for med in MEDS:
        assert med["name"] in task


def test_build_task_rejects_empty_medications():
    with pytest.raises(ValueError, match="at least one medication"):
        build_readback_task("Ravi Kumar", [])


def test_cap_detects_overflow():
    assert exceeds_readback_cap(MEDS) is False
    assert exceeds_readback_cap([MEDS[0]] * (MAX_READBACK_MEDICATIONS + 1)) is True


def test_build_task_raises_over_cap():
    too_many = [MEDS[0]] * (MAX_READBACK_MEDICATIONS + 1)
    with pytest.raises(ValueError, match="exceeds readback cap"):
        build_readback_task("Ravi Kumar", too_many)


def test_result_schema_shape():
    props = READBACK_RESULT_SCHEMA["properties"]
    assert props["reached_patient"]["enum"] == ["yes", "no", "wrong_person"]
    assert props["overall"]["enum"] == ["confirmed", "corrected", "unclear", "refused"]
    item = props["medications"]["items"]["properties"]
    assert item["status"]["enum"] == ["confirmed", "corrected", "unsure"]
    assert "correction_text" in item
    assert set(READBACK_RESULT_SCHEMA["required"]) == {
        "reached_patient",
        "overall",
        "medications",
    }
