import pytest

from medai_readback.adherence import (
    ADHERENCE_RESULT_SCHEMA,
    build_adherence_task,
    needs_escalation,
)


def test_build_task_includes_identity_check_before_medication():
    task = build_adherence_task("Ravi Kumar", "Metformin", "500mg", "morning")
    identity_pos = task.index("Am I speaking with")
    med_pos = task.index("Metformin")
    assert identity_pos < med_pos


def test_build_task_forbids_voicemail_disclosure():
    task = build_adherence_task("Ravi Kumar", "Metformin", "500mg", "morning")
    assert "voicemail" in task.lower()
    assert "Do NOT speak the medication name until identity is confirmed" in task


def test_build_task_includes_medication_dosage_and_slot():
    task = build_adherence_task("Ravi Kumar", "Metformin", "500mg", "Morning")
    assert "Metformin" in task
    assert "500mg" in task
    assert "morning" in task.lower()


def test_build_task_rejects_empty_medication_name():
    with pytest.raises(ValueError, match="medication name"):
        build_adherence_task("Ravi Kumar", "", "500mg", "morning")


def test_build_task_defaults_greeting_when_name_missing():
    task = build_adherence_task("", "Metformin", "500mg", "morning")
    assert "calling there" in task


def test_result_schema_shape():
    props = ADHERENCE_RESULT_SCHEMA["properties"]
    assert props["outcome"]["enum"] == [
        "taken", "already_taken", "not_taken", "refusing", "confused", "no_answer",
    ]
    assert ADHERENCE_RESULT_SCHEMA["required"] == ["outcome"]


@pytest.mark.parametrize(
    "outcome,expected",
    [
        ("taken", False),
        ("already_taken", False),
        ("not_taken", True),
        ("refusing", True),
        ("confused", True),
        ("no_answer", True),
    ],
)
def test_needs_escalation_matrix(outcome, expected):
    assert needs_escalation(outcome) is expected
