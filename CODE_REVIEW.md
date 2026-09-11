# GitHub and local code review — 11 September 2026

## Result

Reviewed the current GitHub main branch in an isolated clone and the local application, OCR, workflow, callback, staff access, browser, operational and legacy example paths. Fixed the concrete local defects below. This is not a claim of perfect code or successful real phone delivery.

GitHub: `nirmalplays/CALL-E`, fetched main `43a953dfcda922085425b5a5e5f227a05a731652`.
Local base: `204b57ac736ab5aeec721b668a8ac31324784421`, plus uncommitted work.
At inventory time: 74 source/configuration/documentation files, 52 absent from the GitHub snapshot and 13 differing from their remote counterparts. This inventory excludes private data, credentials and generated caches; it is not a line-coverage metric.

## GitHub findings

- `medai_readback/calle.py` accepts only HTTP 200 for creation and reads `call_id`. The accepted API call used HTTP 201 and response field `id`. Local code already fixes both.
- The remote client lacks the local explicit live-call switch and stable idempotency header.
- The remote tree lacks the local durable workflow, authenticated dashboard, OCR upload, worker, backup and production entrypoint.
- Its Python/TypeScript examples initiate provider calls outside the durable application's budget. Local examples are now offline-only.
- The remote tests pass while encoding the older response assumptions. Passing that suite is not evidence that the remote project runs the current application.

No remote files, branches or PRs were changed. Local fixes are **not on GitHub**.

## Defects fixed in this review

1. Retired unbudgeted standalone call paths in `test_readback_api.py`, `test_readback_call.py`, and `src/index.ts`/`src/index.js`. Defaults now perform no network requests. Removed the placeholder lunch call; fixture previews are labelled offline.
2. Readback formatting no longer invents “tablet/tablets” for quantities such as “5 ml”. The application and contributed skill preserve the supplied quantity.
3. The main readback prompt no longer says reminders are being set up before scheduling actually occurs.
4. Intake and staff review reject duplicate normalized medicine names. Current confirmation and reminder selection use names, so duplicates could otherwise approve/schedule ambiguously. Distinguish formulation/strength in the name where needed.
5. Blank/oversized timing values are rejected rather than producing an empty instruction.
6. Invalid callback event types and job/provider ID shapes produce validation errors instead of unhandled errors in set membership or SQLite binding.
7. Backup connections are explicitly closed, including failure paths, before cleanup on Windows.
8. Late API/OCR responses cannot repopulate the workspace after lock or overwrite a newer scan selection. Lock clears patient and saved-scan selectors.
9. OCR test images now use Pillow's bundled font instead of a hardcoded Windows font path.
10. The npm test command now invokes real offline verification rather than the default failing placeholder; JavaScript checks and state regressions have explicit commands.

## Evidence

- Local `python verify.py --full`: smoke checks first, then **201 passing tests**. Dummy API key; external sockets blocked. One benign pytest assertion-rewrite warning for already-imported anyio.
- Fetched GitHub snapshot: **41 passing tests**, also with dummy credentials and external sockets blocked.
- JavaScript syntax check passed.
- Separate JavaScript regression passed for late API and OCR responses after lock.
- Retired JavaScript entrypoint executes without API use.
- `git diff --check`: clean.
- `pip check`: no broken installed dependency requirements. This is compatibility checking, not a dependency vulnerability audit.

## Remaining limits

- At the time of this review the only authorized connection test had failed with provider code 404, and no new real calls were made in the review itself. Superseded on 2026-09-11: one authorized confirmation call completed end to end (`call_wO03KFjpByysRKrRHo4abg`). Reminder and caregiver delivery are still unestablished. See README.md and LOCAL_READINESS.md for the current delivery status and its limits.
- OCR draft extraction is conservative text-pattern extraction, not a validated handwritten prescription understanding model. Unknown fields require staff entry. Representative prescription validation remains necessary.
- The production entrypoint is single-clinic, uses named bearer tokens, and requires external TLS/storage/service configuration. No deployment was performed.
- Webhooks use secret per-call URL capabilities, not provider cryptographic signatures. Protect those paths from logs.
- Generic medication/reminder wording and patient/caregiver consent flows still require real-user acceptance validation before clinical use.
- No penetration test, comprehensive dependency vulnerability audit, cross-platform runtime certification or live browser end-to-end recording was completed by these checks. The JavaScript state tests use an isolated DOM stub.
- Legacy fixture modules remain for explicitly labelled offline tests/previews. Production does not register demo routes. Their historical README/demo material must not be presented as evidence of current live success.

Recommended next validation: an authorized representative scan through staff review in the browser, followed by one explicitly approved live call only when a new reason to expect delivery is established. Do not automatically retry the existing failure.
