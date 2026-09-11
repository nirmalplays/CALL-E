---
name: prescription-readback
description: Read an OCR-extracted medication regimen back to a patient by phone, confirm each medication individually in their own language, and route any correction to a human — never scheduling or auto-applying anything until a person confirms. Use when a structured record was extracted from an unreliable source (handwriting OCR, a scanned form) and needs verification with the person it's actually for before it drives downstream automation. Returns a structured per-medication confirmation with any correction captured verbatim.
---

# Prescription readback

The problem this solves isn't specific to medicine: any time you extract a
structured record from something unreliable (handwriting OCR, a scanned
form, a garbled fax) and let that record drive automation, you've made the
extraction step the ground truth. It usually isn't. A phone call to the
person the record is actually about closes that gap before anything
downstream trusts it.

This skill was built for a medication-adherence platform reading back a
prescription scanned from a doctor's handwriting, but the pattern —
identity-gate a call, read a record back item by item, route any
correction to a human instead of applying it — travels to any
extract-then-verify workflow.

## Before you start

You need:
- A CALL-E API key and a phone number you're allowed to call.
- A structured record to read back, shaped as a list of items (see
  `scripts/readback_task.py` for the exact medication-item shape this
  example uses — swap the fields for whatever your record actually is).
- Somewhere to receive the webhook when the call ends, or a plan to poll
  `GET /v1/calls/{id}` instead (the webhook path in `webhook_handler.py`
  is the one this skill recommends — see Workflow).

## Safety boundaries

These aren't suggestions — the task prompt in `readback_task.py` encodes
them directly, and the tests in `scripts/test_readback_task.py` fail if
any of them regress:

1. **Identity before disclosure.** The call confirms it's speaking to the
   actual patient before saying anything about their medication. If
   someone else answers, no detail is shared — just a callback request.
2. **Nothing on voicemail.** A voicemail gets a callback request, never
   the record itself.
3. **Corrections are never auto-applied.** A patient can correct what was
   read back; that correction is captured verbatim and handed to a human.
   It never writes back to the source record on its own — see
   `outcome_routing.py`'s `decide()`, which requires the patient to be
   reached AND have confirmed everything before anything downstream fires.
4. **Overflow routes to a human.** A record with more items than one call
   can reliably review (`MAX_READBACK_MEDICATIONS`, default 6) is rejected
   outright rather than attempted.
5. **Language is never guessed.** Placing a call in a language CALL-E
   hasn't been verified to handle conversationally is worse than not
   calling — resolve the caller's language preference against a known-
   supported list first, and fall back to a human otherwise. (Not
   included in this extract's scripts — see the caller's own
   `locale_support.py` for the pattern, and test it against the live API
   before trusting any language beyond the one you've actually verified.)

## Workflow

```
record → build_readback_task(name, items) → CALL-E call with a
result_schema → wait for the webhook (webhook_handler.py, deduped on the
event id) → decide() the disposition → confirmed: hand off downstream;
corrected/unclear/refused: route to a human queue, change nothing
```

`readback_task.py` and `outcome_routing.py` have no framework or database
dependency — they're pure functions you can call from anything.
`webhook_handler.py` is framework-agnostic too: it takes a plain
`set`-like object for dedup and a callback for what to do with a result,
so you can bind it to FastAPI, Flask, a serverless handler, or a test.

## Cost and safety controls

- **Cap medications per call.** Long calls are unreliable and expensive;
  route anything over the cap to a human instead of forcing it through.
- **Dry-run everything first.** `scripts/demo.py` builds and prints the
  actual task CALL-E would receive, with no network call and no real
  phone number — read it before you ever place a live call.
- **Mask phone numbers everywhere they might be logged, screenshotted, or
  displayed.** Never write a raw number to a log line or a dashboard.

## Dry run

```
cd scripts
python demo.py
```

Prints the exact task prompt and a simulated outcome. No CALL-E API key
needed, no call placed.

## Tests

```
cd scripts
pip install pytest
pytest
```

Covers the safety rules directly — identity-before-disclosure ordering,
voicemail behavior, the auto-apply guard in `decide()`, cap enforcement,
and webhook idempotency.

## Verifying end to end without a real patient call

1. Run `demo.py` and read the printed task — this is what a real patient
   would hear.
2. Feed `outcome_routing.decide()` a handful of hand-written result
   payloads (confirmed / corrected / unclear / refused / not-reached) and
   check the disposition matches what you'd want a human to see.
3. Feed `webhook_handler.handle_calle_event()` a fake terminal-event
   payload twice with the same event id and confirm the second call comes
   back `"duplicate"` — that's the guarantee that a retried webhook
   delivery can't double-process a result.

None of this requires a phone to ring.

## Example

```python
from readback_task import build_readback_task, READBACK_RESULT_SCHEMA
from outcome_routing import decide

medications = [
    {"name": "Metformin", "dosage": "500mg", "quantity": "1",
     "schedule": ["MORNING", "EVENING"], "duration": "30 days",
     "instructions": "after food"},
]

task = build_readback_task("Demo Patient", medications)
# -> send `task` + READBACK_RESULT_SCHEMA to CALL-E's create-call endpoint

# ... later, from your webhook or poll loop:
outcome = decide({"reached_patient": "yes", "overall": "confirmed",
                   "medications": [{"name_as_read": "Metformin", "status": "confirmed"}]}, medications)
# -> "scheduled"
```

Pass `decide(result, expected_medications)` the original pending record retrieved
by call ID. Missing, extra, duplicated, or unsure medication entries cannot proceed.
The return value `scheduled` means eligible for downstream handoff; this pure
function does not schedule anything. The caller must track scheduling success.

## Known limitations

- The medication-item shape here is illustrative, not a standard — adapt
  the fields in `readback_task.py` to whatever record you're reading back.
- Language support is not included in this extract (see Safety boundaries
  above) — it's environment-specific and needs verification against the
  live API before you trust it for anything beyond one language.
- `webhook_handler.py`'s dedup set is in-memory in the example; back it
  with real storage in production so a process restart doesn't forget
  which events it already processed.

## References

- `references/safety.md` — the full reasoning behind each safety rule.
- `references/examples.md` — a worked call transcript, confirmed and
  corrected variants.
