import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from medai_readback.calle import CalleService, _TERMINAL_STATUSES


def _mock_response(status: int, payload: dict):
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=payload)
    resp.text = AsyncMock(return_value=json.dumps(payload))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_call_posts_recipients_as_array_with_metadata(monkeypatch):
    monkeypatch.setenv("CALLE_API_KEY", "calle_test_key")
    svc = CalleService()
    session = MagicMock()
    session.closed = False
    session.post = MagicMock(
        return_value=_mock_response(200, {"call_id": "call_abc123", "status": "queued"})
    )
    svc._session = session

    result = await svc.call(
        to_number="+919876543210",
        task="Read the prescription back.",
        result_schema={"type": "object"},
        metadata={"call_id": "pat1-2026-09-09-readback"},
    )

    assert result == {"status": "call_initiated", "call_sid": "call_abc123"}

    _, kwargs = session.post.call_args
    body = kwargs["json"]
    assert isinstance(body["recipients"], list)
    assert body["recipients"][0]["phones"] == ["+919876543210"]
    assert body["recipients"][0]["region"] == "IN"
    assert body["recipients"][0]["locale"] == "en-IN"
    assert body["metadata"]["call_id"] == "pat1-2026-09-09-readback"
    assert kwargs["headers"]["Authorization"] == "Bearer calle_test_key"


@pytest.mark.asyncio
async def test_call_includes_webhook_url_when_given(monkeypatch):
    monkeypatch.setenv("CALLE_API_KEY", "calle_test_key")
    svc = CalleService()
    session = MagicMock()
    session.closed = False
    session.post = MagicMock(
        return_value=_mock_response(200, {"call_id": "c1", "status": "queued"})
    )
    svc._session = session

    await svc.call(
        to_number="+919876543210",
        task="t",
        result_schema={},
        metadata={"call_id": "x"},
        webhook_url="https://example.test/medai/calle/webhook",
    )

    _, kwargs = session.post.call_args
    assert kwargs["json"]["webhook_url"] == "https://example.test/medai/calle/webhook"


@pytest.mark.asyncio
async def test_call_raises_on_non_200(monkeypatch):
    monkeypatch.setenv("CALLE_API_KEY", "calle_test_key")
    svc = CalleService()
    session = MagicMock()
    session.closed = False
    session.post = MagicMock(return_value=_mock_response(422, {"detail": "bad"}))
    svc._session = session

    with pytest.raises(Exception, match="CALL-E API error"):
        await svc.call(
            to_number="+919876543210",
            task="t",
            result_schema={},
            metadata={"call_id": "x"},
        )


@pytest.mark.asyncio
async def test_call_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("CALLE_API_KEY", raising=False)
    svc = CalleService()
    with pytest.raises(ValueError, match="CALLE_API_KEY"):
        await svc.call(
            to_number="+919876543210",
            task="t",
            result_schema={},
            metadata={"call_id": "x"},
        )


@pytest.mark.asyncio
async def test_get_call_details_marks_completed_terminal(monkeypatch):
    monkeypatch.setenv("CALLE_API_KEY", "calle_test_key")
    svc = CalleService()
    session = MagicMock()
    session.closed = False
    session.get = MagicMock(
        return_value=_mock_response(
            200, {"status": "completed", "structured_result": {"overall": "confirmed"}}
        )
    )
    svc._session = session

    details = await svc.get_call_details("call_abc123")

    assert details["status"] == "completed"
    assert details["state"] == "terminal"
    assert details["call_details"]["structured_result"]["overall"] == "confirmed"


@pytest.mark.asyncio
async def test_get_call_details_marks_in_progress_active(monkeypatch):
    monkeypatch.setenv("CALLE_API_KEY", "calle_test_key")
    svc = CalleService()
    session = MagicMock()
    session.closed = False
    session.get = MagicMock(return_value=_mock_response(200, {"status": "in_progress"}))
    svc._session = session

    details = await svc.get_call_details("call_abc123")
    assert details["state"] == "active"


def test_terminal_statuses_match_calle_spec():
    assert _TERMINAL_STATUSES == frozenset(["completed", "failed", "canceled"])
