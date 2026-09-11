import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _reset_store(monkeypatch):
    monkeypatch.setenv("MEDAI_ENABLE_LEGACY_DEMO", "true")
    monkeypatch.setenv("MEDAI_OFFLINE_TEST", "true")
    app_module.db._collections.clear()
    yield
    app_module.db._collections.clear()


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_scans_returns_known_fixtures():
    resp = client.get("/demo/scans")
    assert resp.status_code == 200
    assert "demo-clean" in resp.json()["scan_ids"]


def test_unknown_scan_id_is_reported_without_placing_a_call(monkeypatch):
    called = {"value": False}

    async def fake_call(self, *a, **k):
        called["value"] = True

    monkeypatch.setattr(app_module.CalleService, "call", fake_call)

    resp = client.post(
        "/demo/readback-call",
        json={"scan_id": "not-a-real-scan", "phone": "+919876543210"},
    )
    assert resp.status_code == 200
    assert "error" in resp.json()
    assert called["value"] is False


def test_unsupported_language_falls_back_without_calling_calle(monkeypatch):
    """PRD A3 — never place a call in a language the patient didn't choose."""
    called = {"value": False}

    async def fake_call(self, *a, **k):
        called["value"] = True

    monkeypatch.setattr(app_module.CalleService, "call", fake_call)

    resp = client.post(
        "/demo/readback-call",
        json={
            "scan_id": "demo-clean",
            "phone": "+919876543210",
            "language_preference": "hi-IN",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fallback"] == "unsupported_language"
    assert body["supported_locales"] == ["en-IN"]
    assert called["value"] is False


def test_supported_language_places_call_with_resolved_locale(monkeypatch):
    monkeypatch.setenv("CALLE_API_KEY", "calle_test_key")
    captured = {}

    async def fake_call(self, to_number, task, result_schema, metadata,
                         webhook_url=None, region=None, locale=None):
        captured["locale"] = locale
        captured["to_number"] = to_number
        captured["call_id"] = metadata["call_id"]
        return {"status": "call_initiated", "call_sid": "call_123"}

    monkeypatch.setattr(app_module.CalleService, "call", fake_call)

    resp = client.post(
        "/demo/readback-call",
        json={
            "scan_id": "demo-misread-dose",
            "phone": "+919876543210",
            "language_preference": "en-IN",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["calle"]["call_sid"] == "call_123"
    assert captured["locale"] == "en-IN"
    assert captured["to_number"] == "+919876543210"
    assert body["call_id"] == captured["call_id"]


def test_confirmations_list_reflects_placed_calls(monkeypatch):
    async def fake_call(self, *a, **k):
        return {"status": "call_initiated", "call_sid": "call_456"}

    monkeypatch.setattr(app_module.CalleService, "call", fake_call)

    resp = client.post(
        "/demo/readback-call",
        json={"scan_id": "demo-clean", "phone": "+919876543210"},
    )
    call_id = resp.json()["call_id"]

    resp = client.get("/demo/confirmations")
    assert resp.status_code == 200
    ids = [doc["call_id"] for doc in resp.json()]
    assert call_id in ids
