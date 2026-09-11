import pytest

from medai_readback.escalation import ESCALATION_RESULT_SCHEMA, build_escalation_task


def test_build_task_names_caregiver_and_patient():
    task = build_escalation_task("Sunita", "Ravi Kumar", "Metformin", "not_taken")
    assert "Sunita" in task
    assert "Ravi Kumar" in task
    assert "Metformin" in task


def test_build_task_rejects_empty_caregiver_name():
    with pytest.raises(ValueError, match="caregiver"):
        build_escalation_task("", "Ravi Kumar", "Metformin", "not_taken")


def test_build_task_rejects_empty_patient_name():
    with pytest.raises(ValueError, match="patient"):
        build_escalation_task("Sunita", "", "Metformin", "not_taken")


@pytest.mark.parametrize(
    "outcome,phrase",
    [
        ("not_taken", "did not take"),
        ("refusing", "declined to take"),
        ("confused", "was unsure about"),
        ("no_answer", "could not be reached about"),
    ],
)
def test_build_task_uses_outcome_specific_phrase(outcome, phrase):
    task = build_escalation_task("Sunita", "Ravi Kumar", "Metformin", outcome)
    assert phrase in task


def test_build_task_includes_patient_reason_when_given():
    task = build_escalation_task(
        "Sunita", "Ravi Kumar", "Metformin", "refusing", patient_reason="it makes me nauseous"
    )
    assert "it makes me nauseous" in task


def test_build_task_omits_reason_line_when_not_given():
    task = build_escalation_task("Sunita", "Ravi Kumar", "Metformin", "not_taken")
    assert "They told us" not in task


def test_build_task_does_not_offer_medical_advice():
    task = build_escalation_task("Sunita", "Ravi Kumar", "Metformin", "not_taken")
    assert "Do not give medical advice" in task


def test_result_schema_shape():
    props = ESCALATION_RESULT_SCHEMA["properties"]
    assert props["reached_caregiver"]["enum"] == ["yes", "no"]
    assert ESCALATION_RESULT_SCHEMA["required"] == ["reached_caregiver"]


def test_escalation_gates_clinical_script_on_identity():
    task = build_escalation_task("Sunita", "Ravi Kumar", "Metformin", "not_taken")
    greeting = task.split('First confirm identity. Say: "', 1)[1].split('"', 1)[0]
    assert "Sunita" in greeting
    assert "Ravi Kumar" not in greeting
    assert "Metformin" not in greeting
    assert "Only after the registered caregiver confirms identity" in task
    assert "Never leave patient or medication details on voicemail" in task
