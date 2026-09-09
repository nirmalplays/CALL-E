import pytest

from outcome_routing import decide


@pytest.mark.parametrize(
    "structured,expected",
    [
        ({"reached_patient": "yes", "overall": "confirmed"}, "scheduled"),
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
