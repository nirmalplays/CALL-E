# MedAI × CALL-E

Prescription uploads, local OCR, staff review, and budget-controlled CALL-E prescription confirmation and reminder workflows.

**Status:** functioning local application with real image/PDF extraction and persistent records. One authorized live CALL-E call has now completed end to end (2026-09-11, call `call_wO03KFjpByysRKrRHo4abg`): a single-medication readback to a consenting `+91` mobile in `en-IN`, with a structured result extracted and stored. That supersedes the earlier `404` connection failure, but it is one call on one number — webhook delivery, reminder/caregiver flows and the correction path remain unverified. Calls are disabled by default. This is a hackathon application, not a clinically validated medical system.

## Run locally

Use Python 3.14. In a virtual environment:

```text
python -m pip install -r requirements.txt -r requirements-ocr.txt
```

Copy `.env.example` to `.env`. Generate a staff access token with:

```text
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `MEDAI_STAFF_TOKEN` to that token. Keep `CALLE_ENABLE_LIVE_CALLS=false` and `CALLE_CALL_BUDGET=0`. No provider key is needed for local OCR, review, storage, or offline verification.

```text
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open `http://127.0.0.1:8000/local/dashboard` and unlock with the staff token. The token stays in browser memory; reload or lock requires authentication again.

## Actual workflow

1. Add or select a patient and record their consent and preferred language.
2. Upload PNG, JPEG, WebP or PDF. OCR runs locally, without sending documents to an external API.
3. Load editable draft medicine fields derived from the recognized text. Missing fields stay blank. Compare every value with the original; handwriting accuracy is not validated.
4. Save reviewed medication data. Original files and extracted text remain available through authenticated saved-scan endpoints. No fixture substitutes for an uploaded file.
5. Preview the confirmation call. Live dispatch requires explicit configuration, an allowed number, verified locale, HTTPS callback and remaining local budget. The dashboard's Call readiness panel names each missing setting and the environment variable that supplies it, and shows how much of the local budget is reserved.
6. Call corrections go to staff review. Approved regimens can receive explicitly scheduled reminder jobs. Creating a schedule does not place a call; a reminder is either dialled by hand from the Reminders view once it falls due, or by the worker, which must be explicitly enabled.
7. A submitted call stays unresolved until its outcome is known. Reopen the prescription and use **Check outcome with provider** to read the outcome back; a dispatch the provider never confirmed is marked *Outcome unknown*, keeps its reserved budget, and is never redialled automatically.

The database defaults to `data/medai.sqlite3`. Use one clinic per database/process. Backups contain prescription data and need the same access protection as the source database.

## Verify without spending credits

```text
python verify.py --full
node --check medai_readback/local_dashboard.js
node tests/test_ui_state.cjs medai_readback/local_dashboard.js
```

`tests/test_dashboard_calls.cjs` covers the call-placement paths (readiness, dispatch gating, reconcile, reminder dispatch) and runs under pytest via `tests/test_dashboard_calls.py`, which also pins the dashboard's setup guidance to the blocker strings `live_settings()` emits.

Verification runs smoke checks first, uses dummy credentials and blocks external sockets. The reviewed revision passes 210 Python tests plus the JavaScript state regression. OCR checks use generated documents, not real patient records. Node is needed only for the JavaScript checks.

## Calls and worker

Live settings are listed in `.env.example` and checked by `/local/readiness`. An accepted provider request is not proof that the phone connected. Dispatch reservations are durable; uncertain responses retain the budget and cannot automatically redial.

Without a public HTTPS callback the terminal webhook can never arrive, so a submitted call would stay unresolved. `POST /local/confirmations/{call_id}/reconcile` reads that call's state from the provider and applies the same outcome rules as the webhook, resolving the record. It places no call, spends no budget, works with live calling disabled, and is safe to repeat or to race with a late webhook. It needs a provider call ID, so it cannot resolve a dispatch whose outcome was never returned. The dashboard exposes this as **Check outcome with provider** on any prescription awaiting an outcome.

```text
python worker.py --once
```

The default worker is a dry run. `--live` opts into dispatch and still requires all call settings. Do not enable it until a controlled live test succeeds. All historical `test_readback_*.py` and `src/index.*` examples are now offline-only, so they cannot bypass application dispatch controls.

## Documentation

- [OCR installation and behavior](OCR_SETUP.md)
- [Local workflow and readiness](LOCAL_READINESS.md)
- [Production configuration and release gates](PRODUCTION.md)
- [GitHub/local code review and test evidence](CODE_REVIEW.md)
- [Reusable contribution](skills/prescription-readback/SKILL.md)

The production entrypoint `production:create_app` excludes legacy demo routes and requires named staff keys, explicit allowed hosts and persistent storage. It does not make the application clinically validated or resolve provider routing.

## Scope and limitations

- OCR drafts use conservative text patterns; no automatic clinical interpretation, invented medicines or inferred doses.
- Exotel and the original medai-multitenant platform are not included. The Exotel adapter is an explicit unsupported stub.
- Webhooks use secret per-call URL capabilities, not provider signatures. Keep callback paths out of access logs.
- `ocr/main.py` and historical demo modules contain labelled offline fixtures. They are not part of the real upload path; demo endpoints are disabled by default.
- Phone delivery is proven only for the single confirmation call described above. Delivery was also unreliable: of four authorized attempts to the same number, three failed at the carrier before conversation (`NO ANSWER` twice, `FAILED` once) and only the answered attempt connected. Successful reminder/caregiver calls, the correction path, multi-medication readback and representative handwritten prescriptions still need validation.

This repository extends pre-existing MedAI/CALL-E adapter and test work with the OCR, review, durable workflow and reusable contribution. Historical demo instructions in `DEMO.md` describe the original fixture demonstration and do not establish live success.
