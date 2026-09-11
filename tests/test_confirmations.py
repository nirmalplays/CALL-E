import pytest

from medai_readback.confirmations import (
    CONFIRMATIONS_COLLECTION,
    build_confirmation_call_id,
    create_pending_confirmation,
    decide,
    resolve_confirmation,
    set_on_confirmed,
)
from medai_readback.store import InMemoryDB

MEDS = [
    {
        "name": "Metformin",
        "dosage": "500mg",
        "quantity": "1",
        "schedule": ["MORNING"],
        "duration": "30 days",
        "instructions": "after food",
    }
]


@pytest.fixture
def db():
    return InMemoryDB()


@pytest.fixture(autouse=True)
def hook():
    """Capture on_confirmed invocations and restore the default afterwards."""
    calls = []

    async def capture(doc):
        calls.append(doc)

    set_on_confirmed(capture)
    yield calls

    async def noop(doc):
        return None

    set_on_confirmed(noop)


async def _seed(db, patient_id="p1"):
    return await create_pending_confirmation(
        db,
        patient_id=patient_id,
        phone_number="+919876543210",
        patient_name="Ravi",
        age="61",
        gender="male",
        medications=MEDS,
        enrollment_days=30,
    )


def test_call_id_is_deterministic_per_patient_and_day():
    cid = build_confirmation_call_id("pat123")
    assert cid.startswith("pat123-")
    assert cid.endswith("-readback")
    assert build_confirmation_call_id("pat123") == cid


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


@pytest.mark.asyncio
async def test_create_pending_stores_medications_and_status(db):
    call_id = await _seed(db, "pat123")
    doc = await db.get_collection(CONFIRMATIONS_COLLECTION).find_one({"call_id": call_id})
    assert doc["status"] == "pending"
    assert doc["medications"] == MEDS
    assert doc["patient_id"] == "pat123"


@pytest.mark.asyncio
async def test_rescan_same_day_does_not_duplicate(db):
    first = await _seed(db, "pat123")
    second = await _seed(db, "pat123")
    assert first == second
    assert await db.get_collection(CONFIRMATIONS_COLLECTION).count() == 1


@pytest.mark.asyncio
async def test_confirmed_outcome_invokes_hook(db, hook):
    call_id = await _seed(db)
    outcome = await resolve_confirmation(
        db, call_id,
        {"reached_patient": "yes", "overall": "confirmed",
         "medications": [{"name_as_read": "Metformin", "status": "confirmed"}]},
    )
    assert outcome == "scheduled"
    assert len(hook) == 1


@pytest.mark.asyncio
async def test_corrected_stores_verbatim_and_does_not_invoke_hook(db, hook):
    call_id = await _seed(db)
    outcome = await resolve_confirmation(
        db, call_id,
        {"reached_patient": "yes", "overall": "corrected",
         "medications": [{"name_as_read": "Metformin", "status": "corrected",
                          "correction_text": "one tablet not two"}]},
    )
    assert outcome == "review"
    doc = await db.get_collection(CONFIRMATIONS_COLLECTION).find_one({"call_id": call_id})
    assert doc["corrections"][0]["correction_text"] == "one tablet not two"
    assert hook == []


@pytest.mark.asyncio
async def test_confirmed_but_not_reached_does_not_invoke_hook(db, hook):
    """A model returning confirmed without reaching the patient must not proceed."""
    call_id = await _seed(db)
    outcome = await resolve_confirmation(
        db, call_id,
        {"reached_patient": "no", "overall": "confirmed", "medications": []},
    )
    assert outcome == "fallback"
    assert hook == []


@pytest.mark.asyncio
async def test_resolve_is_idempotent(db, hook):
    call_id = await _seed(db)
    result = {"reached_patient": "yes", "overall": "confirmed",
              "medications": [{"name_as_read": "Metformin", "status": "confirmed"}]}
    assert await resolve_confirmation(db, call_id, result) == "scheduled"
    assert await resolve_confirmation(db, call_id, result) == "scheduled"
    assert len(hook) == 1, "a replayed result must not re-trigger the hook"


@pytest.mark.asyncio
async def test_unknown_call_id_returns_unknown(db):
    assert await resolve_confirmation(db, "nope", {"overall": "confirmed"}) == "unknown"


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


@pytest.mark.asyncio
@pytest.mark.parametrize("medications", [None, [], [None], [{"name_as_read": "Other", "status": "confirmed"}]])
async def test_incomplete_result_never_invokes_scheduler(db, hook, medications):
    call_id = await _seed(db)
    result = {"reached_patient": "yes", "overall": "confirmed", "medications": medications}
    assert await resolve_confirmation(db, call_id, result) == "fallback"
    assert hook == []
