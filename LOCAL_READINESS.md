# Local workflow and readiness

The new supported entry point is `/local/dashboard`. Legacy fixture routes are
disabled by default. Do not enable them for a live deployment.

## Local setup (PowerShell)

Install `requirements.txt`, then set a random staff token locally:

```powershell
$env:MEDAI_STAFF_TOKEN = (python -c "import secrets; print(secrets.token_urlsafe(32))")
$env:MEDAI_TENANT_ID = 'local'
$env:CALLE_ENABLE_LIVE_CALLS = 'false'
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Use the token from your terminal environment to unlock `/local/dashboard`.
The token is held in browser memory, not localStorage. Restarting the server
does not erase the SQLite database at `data/medai.sqlite3`. Override with
`MEDAI_DB_PATH`. Protect this directory and exclude it from Git and backups
shared publicly; it contains patient information and webhook capabilities.

Staff API requests use `Authorization: Bearer <MEDAI_STAFF_TOKEN>`:

1. `PUT /local/patients`: `patient_id`, `name`, E.164 `phone`, `language`,
   two-letter `region`, explicit `consent`, and `consent_evidence`.
2. `POST /local/intakes`: `patient_id`, unique `source_id`, and `medications`
   containing name, dosage, quantity, schedule, duration and instructions.
   These are actual submitted extraction data; no fixture is substituted.
3. `GET /local/confirmations/{call_id}/preview`: inspect the exact task,
   result schema and live blockers. Does not call any API.
4. Review/fallback records appear in the dashboard. Staff edit and approve a
   separate regimen with a reason. Original extraction remains unchanged.
5. After approval, enter explicit reminder timestamps with timezones. Jobs
   are durably stored and duplicate timestamps do not duplicate jobs.
6. `GET /local/jobs` lists saved reminder jobs. Use `python worker.py --once` to preview due jobs with no calls.
   The worker dispatches only with `--live` and all credit controls configured.

Consent withdrawal through `PUT /local/patients` blocks new intake/dispatch/
approval/scheduling and cancels pending jobs. An already accepted provider
call cannot be recalled by this local application.

## Credit protection

Live calls are OFF by default, including direct adapter calls. Before a live
test the operator must be told the target, scenario and maximum call count.
Do not enable or dial during offline verification.

The authenticated dispatch endpoint requires all of:

- `CALLE_ENABLE_LIVE_CALLS=true`
- `CALLE_CALL_BUDGET`: explicit maximum total locally reserved calls (default 0)
- `CALLE_ALLOWED_PHONES`: explicit comma-separated test recipients
- `CALLE_VERIFIED_LOCALES`: only languages actually validated conversationally
- `MEDAI_PUBLIC_BASE_URL`: public HTTPS origin/base path routing to this server
- `CALLE_API_KEY`

The persistent reservation is conservative: errors/timeouts do not refund it,
because a call may have been accepted. Calls cannot be redialed automatically.
The adapter sends the stable call ID as `Idempotency-Key`. The local budget
is not the provider's balance and must not be described as remaining credits.

## Webhooks

The receiver expects the documented `id`, `type`, `data` envelope and validates
`CALL-E-Event-Id`, metadata (tenant/patient/call), and the provider call ID.
Each dispatch includes an unguessable per-call HTTPS callback URL. This is
application capability authentication, not a CALL-E cryptographic signature.
Keep these URLs out of access logs; run uvicorn with `--no-access-log` and
configure any tunnel/reverse proxy accordingly. Processing and event recording
are atomic in SQLite, so failed transactions remain retryable.

Public API contract checked without the account key:
https://docs.heycall-e.com/api-reference/calls

## Reconciliation without a callback

When `MEDAI_PUBLIC_BASE_URL` does not resolve to this server, the terminal
webhook cannot be delivered and a submitted confirmation stays `pending` with
`dispatch_state=submitted`. `POST /local/confirmations/{call_id}/reconcile`
(staff auth) reads that call from the provider and applies the same outcome
rules as the webhook receiver, so a polled result and a delivered one cannot
disagree. It places no call and reserves no budget, so it is allowed while
`CALLE_ENABLE_LIVE_CALLS=false`. Repeating it reports the existing disposition
and changes nothing; a webhook arriving afterwards is recorded but will not
re-resolve the record. It requires a stored provider call ID, so a dispatch left
in `dispatch_state=unknown` still has to be reconciled manually with the
provider — this endpoint cannot recover a call ID that was never returned.

## What is not yet verified or integrated

- One authorized live confirmation call completed end to end on 2026-09-11
  (`call_wO03KFjpByysRKrRHo4abg`): identity check, single-medication readback,
  patient confirmation, and a structured result matching the schema, resolved
  into the durable record through the reconcile endpoint. That is one call, to
  one consenting number, in `en-IN`, with one medication and no correction.
- Real webhook delivery is still unverified: that call used a placeholder
  callback URL and was resolved by reconciliation, not by a delivered event.
  Duplicate-event replay against a real provider event is likewise unverified.
- Delivery was not reliable. Four authorized attempts to the same number
  produced one connected conversation; three failed at the carrier before any
  conversation (`NO ANSWER` twice, `FAILED` once). Treat single-attempt
  delivery as unproven and expect retries to be necessary.
- Local image/PDF OCR is installed; see OCR_SETUP.md. Medication fields still require staff entry and review. Submit reviewed extraction through the intake API;
  do not describe this as an implemented image-to-text model.
- Adherence/escalation dispatch is available through the explicit live worker,
  but has only been tested with simulated provider responses. The original
  Exotel/platform integration is not available locally.
- Single local staff credential and single tenant are intentional local scope;
  this is not a production multi-user identity system.

Review code, run offline smoke checks, then regression/integration tests. Only
after those pass and external configuration is available should a notified,
bounded live test be arranged. No commit or push is part of this work.


## Due-job worker

Scheduling requires `medication_names` explicitly selected from the approved
regimen; no medication times or PRN rules are inferred. Jobs are per medication.
`python worker.py --once` is always a zero-call preview. `--live` explicitly opts
into outbound calls and still requires budget, allowlist, consent, configured
HTTPS callbacks, and verified recipient locale. Repeated ticks cannot redial
submitted jobs. Adherence failure outcomes can queue caregiver escalation, which
uses the same budget and requires the caregiver's own language, region, phone
and name in the patient record. No caregiver language is guessed.


## Verification performed

Use `python verify.py` for smoke checks first, or `python verify.py --full`
for smoke followed by all regression tests. Both override the account key with
an offline value and block external sockets. Current regression baseline:
209 passing tests. Verification itself makes no live calls or authenticated
provider requests; the live call recorded above was placed separately, with
explicit authorization and a budget of one call per attempt.
