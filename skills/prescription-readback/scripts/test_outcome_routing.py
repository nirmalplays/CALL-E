import pytest

from outcome_routing import decide


@pytest.mark.parametrize(
    "structured,expected",
    [
        ({"reached_patient": "yes", "overall": "confirmed"}, "fallback"),
        ({"reached_patient": "yes", "overall": "corrected"}, "review"),
        ({"reached_patient": "yes", "overall": "unclear"}, "fallback"),
        ({"reached_patient": "yes", "overall": "refused"}, "fallback"),
        ({"reached_patient": "no", "overall": "confirmed"}, "fallback"),
        ({"reached_patient": "wrong_person", "overall": "confirmed"}, "fallback"),
        ({}, "fallback"),
    ],
)
def test_decide_matrix(structured, expected):
    assert decide(structured) == expected


def test_a_model_claiming_confirmed_without_reaching_patient_never_schedules():
    """The failure mode from references/safety.md: overall says confirmed,
    reached_patient says no — this must never reach 'scheduled'."""
    assert decide({"reached_patient": "no", "overall": "confirmed"}) == "fallback"


@pytest.mark.parametrize("medications,expected", [
    (None, "fallback"), ([], "fallback"), ([None], "fallback"),
    ([{"name_as_read": "Metformin", "status": "unsure"}], "fallback"),
    ([{"name_as_read": "Metformin", "status": "corrected"}], "review"),
    ([{"name_as_read": "Metformin", "status": "confirmed", "correction_text": "one not two"}], "review"),
    ([{"name_as_read": "Other", "status": "confirmed"}], "fallback"),
    ([{"name_as_read": "Metformin", "status": "confirmed"}] * 2, "fallback"),
    ([{"name_as_read": "Metformin", "status": "confirmed", "correction_text": 42}], "fallback"),
    ([{"name_as_read": " metFORMIN ", "status": "confirmed", "correction_text": None}], "scheduled"),
])
def test_per_medication_validation(medications, expected):
    result = {"reached_patient": "yes", "overall": "confirmed", "medications": medications}
    assert decide(result, [{"name": "Metformin"}]) == expected


def test_missing_regimen_context_never_approves():
    result = {"reached_patient": "yes", "overall": "confirmed",
              "medications": [{"name_as_read": "Metformin", "status": "confirmed"}]}
    assert decide(result) == "fallback"
    assert decide(result, [{"name": "Metformin"}, {"name": "Amoxicillin"}]) == "fallback"
    assert decide(result, [{"name": "Metformin"}, {"name": "Metformin"}]) == "fallback"


@pytest.mark.parametrize("result", [None, [], "confirmed", 1])
def test_malformed_result_fails_closed(result):
    assert decide(result, [{"name": "Metformin"}]) == "fallback"
