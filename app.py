"""FastAPI entrypoint — webhook receiver + a small demo endpoint, sharing one
in-memory store.

The webhook receiver (medai_readback/webhooks.py) and the code that places a
call must share the same db instance for a pending confirmation to resolve —
InMemoryDB only works within one process, so both live here rather than in a
separate one-off script. demo_call.py talks to this server over HTTP for a
live call; it also has a --dry-run mode that needs no server at all.

Run with:
    uvicorn app:app --reload

Then, with CALLE_WEBHOOK_URL in .env pointed at this server's /calle/webhook
(ngrok or similar tunnel during a live recording):

    python demo_call.py demo-misread-dose --phone +91XXXXXXXXXX
    curl localhost:8000/demo/confirmations
"""

from __future__ import annotations

import os

import env_config  # noqa: F401 — side effect: loads .env into os.environ before CalleService reads it

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from loguru import logger

from medai_readback.calle import CalleService
from medai_readback.confirmations import CONFIRMATIONS_COLLECTION, create_pending_confirmation
from medai_readback.dashboard import render_dashboard
from medai_readback.locale_support import resolve_locale, supported_locales
from medai_readback.readback import READBACK_RESULT_SCHEMA, build_readback_task
from medai_readback.store import InMemoryDB
from medai_readback.webhooks import router as calle_router
from medai_readback.webhooks import set_db
from ocr.main import available_scan_ids, extract_prescription

app = FastAPI(title="MedAI CALL-E readback demo")
app.include_router(calle_router)

# Shared by every route below — swap for a real Motor client in production,
# see medai_readback/store.py.
db = InMemoryDB()
set_db(db)


class ReadbackCallRequest(BaseModel):
    scan_id: str
    phone: str
    language_preference: str = "en-IN"


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/demo/scans")
async def list_scans():
    return {"scan_ids": available_scan_ids()}


@app.get("/demo/confirmations")
async def list_confirmations():
    """Everything recorded so far — the correction review queue for the demo."""
    col = db.get_collection(CONFIRMATIONS_COLLECTION)
    return await col.find_all()


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """PRD G2 — the correction-review surface staff actually look at,
    grouped so anything needing a decision (review, fallback) sorts first."""
    col = db.get_collection(CONFIRMATIONS_COLLECTION)
    return render_dashboard(await col.find_all())


@app.post("/demo/readback-call")
async def place_readback_call(body: ReadbackCallRequest):
    """OCR fixture -> readback task -> CALL-E call -> pending confirmation,
    all in this process so the webhook can resolve it once the call ends."""
    try:
        scan = extract_prescription(body.scan_id)
    except KeyError as exc:
        return {"error": str(exc), "known_scan_ids": available_scan_ids()}

    # PRD A3: never place a call in a language the patient didn't choose.
    # Unsupported (or not yet verified) -> fall back to dashboard staff
    # review instead of guessing a substitute language.
    locale = resolve_locale(body.language_preference)
    if locale is None:
        logger.warning(
            "Readback call for scan_id={} skipped — unsupported language_preference={}",
            body.scan_id, body.language_preference,
        )
        return {
            "fallback": "unsupported_language",
            "language_preference": body.language_preference,
            "supported_locales": sorted(supported_locales()),
        }

    task = build_readback_task(scan["patient_name"], scan["medications"])
    call_id = await create_pending_confirmation(
        db,
        patient_id=body.scan_id,
        phone_number=body.phone,
        patient_name=scan["patient_name"],
        age="61",
        gender="unspecified",
        medications=scan["medications"],
        enrollment_days=30,
    )

    service = await CalleService.get_instance()
    result = await service.call(
        to_number=body.phone,
        task=task,
        result_schema=READBACK_RESULT_SCHEMA,
        metadata={"call_id": call_id, "patient_id": body.scan_id},
        webhook_url=os.getenv("CALLE_WEBHOOK_URL") or None,
        locale=locale,
    )

    return {"call_id": call_id, "calle": result}
