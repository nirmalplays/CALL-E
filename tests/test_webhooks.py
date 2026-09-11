import pytest

from medai_readback.confirmations import (
    create_pending_confirmation,
    set_on_confirmed,
)
from medai_readback.store import InMemoryDB
from medai_readback.webhooks import (
    WEBHOOK_EVENTS_COLLECTION,
    handle_event,
    router,
)

MEDS = [
    {"name": "Metformin", "dosage": "500mg", "quantity": "1",
     "schedule": ["MORNING"], "duration": "30 days", "instructions": "after food"}
]


@pytest.fixture
def db():
    return InMemoryDB()


@pytest.fixture(autouse=True)
def hook():
    calls = []

    async def capture(doc):
        calls.append(doc)

    set_on_confirmed(capture)
    yield calls


async def _seed(db, patient_id="p1"):
    return await create_pending_confirmation(
        db, patient_id=patient_id, phone_number="+919876543210",
        patient_name="Ravi", age="61", gender="male",
        medications=MEDS, enrollment_days=30,
    )


def _payload(call_id, event="call.completed", structured=None):
    return {
        "event": event,
        "metadata": {"call_id": call_id, "patient_id": "p1"},
        "structured_result": structured
        if structured is not None
        else {
            "reached_patient": "yes",
            "overall": "confirmed",
            "medications": [{"name_as_read": "Metformin", "status": "confirmed"}],
        },
    }


def test_router_exposes_webhook_path():
    assert router.prefix == "/calle"
    assert "/calle/webhook" in [r.path for r in router.routes]


@pytest.mark.asyncio
async def test_missing_call_id_is_rejected(db):
    result = await handle_event(db, "evt_1", {"event": "call.completed", "metadata": {}})
    assert result["status"] == "ignored"
    assert "call_id" in result["reason"]


@pytest.mark.asyncio
async def test_confirmed_result_is_routed(db):
    call_id = await _seed(db)
    result = await handle_event(db, "evt_1", _payload(call_id))
    assert result["status"] == "processed"
    assert result["disposition"] == "scheduled"


@pytest.mark.asyncio
async def test_duplicate_event_id_is_not_reprocessed(db, hook):
    call_id = await _seed(db)
    first = await handle_event(db, "evt_1", _payload(call_id))
    second = await handle_event(db, "evt_1", _payload(call_id))
    assert first["status"] == "processed"
    assert second["status"] == "duplicate"
    assert len(hook) == 1


@pytest.mark.asyncio
async def test_event_is_recorded_for_audit(db):
    call_id = await _seed(db)
    await handle_event(db, "evt_1", _payload(call_id))
    doc = await db.get_collection(WEBHOOK_EVENTS_COLLECTION).find_one({"event_id": "evt_1"})
    assert doc is not None
    assert doc["call_id"] == call_id


@pytest.mark.asyncio
async def test_failed_call_routes_to_fallback(db, hook):
    call_id = await _seed(db)
    result = await handle_event(db, "evt_2", _payload(call_id, event="call.failed", structured={}))
    assert result["disposition"] == "fallback"
    assert hook == []


@pytest.mark.asyncio
async def test_result_validation_failed_is_terminal(db):
    call_id = await _seed(db)
    result = await handle_event(
        db, "evt_3", _payload(call_id, event="call.result_validation_failed", structured={})
    )
    assert result["status"] == "processed"


@pytest.mark.asyncio
async def test_non_terminal_event_ignored(db):
    result = await handle_event(
        db, "evt_4", {"event": "call.started", "metadata": {"call_id": "x"}}
    )
    assert result["status"] == "ignored"


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["call.failed", "call.result_validation_failed"])
async def test_failed_event_cannot_approve_even_with_confirmed_payload(db, hook, event):
    call_id = await _seed(db)
    result = await handle_event(db, "contradiction", _payload(call_id, event=event))
    assert result["disposition"] == "fallback"
    assert hook == []
