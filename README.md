# MedAI × CALL-E — voice prescription readback

**Hackathon:** CALL-E: Your Code Is Calling (Devpost) · **Deadline:** 14 Sep 2026, 21:15 IST

MedAI scans handwritten prescriptions via OCR and places scheduled
adherence calls through Exotel. In Indian outpatient care, handwriting is
often the only thing a patient takes home — and nothing today checks OCR's
extraction against what the doctor actually said before it drives
reminders. This project adds that check: after a scan, CALL-E reads the
extracted regimen back to the patient and captures a structured,
per-medication confirmation before anything is scheduled. It also ports
MedAI's adherence and escalation calls onto CALL-E as a second telephony
provider.

Full requirements: see the PRD (`extract_prd.py` pulled its text out of the
original PDF into this repo's early exploration — the source PRD isn't
otherwise included here).

## What's built

| Goal | Status |
|---|---|
| **G1** Readback call, per-medication, structured outcome | Done — `medai_readback/readback.py`, `ocr/main.py` (fixture-backed), wired end to end in `app.py` |
| **G2** Corrections routed to a human, never silently applied | Done — `medai_readback/confirmations.py`'s `decide()`, surfaced at `/dashboard` |
| **G3** CALL-E as a config-selectable provider alongside Exotel | Scaffolded — `medai_readback/provider.py` selects by config; the Exotel side is a deliberate stub (see Known gaps) |
| **G4** Extracted, standalone community contribution | Done — `skills/prescription-readback/`, matches `CALLE-AI/awesome-phone-call-agents`'s own template |
| **A3** Never place a call in an unverified language | Done — `medai_readback/locale_support.py` defaults to `en-IN` only until the real API is tested |
| Adherence + escalation call taxonomy | Ported — `medai_readback/adherence.py`, `medai_readback/escalation.py` |

98 tests passing (`tests/`), plus 19 more inside the standalone community
package (`skills/prescription-readback/scripts/`, run independently — see
its own `SKILL.md`).

## Relationship to the MedAI platform

**This repo does not contain the MedAI platform.** The PRD describes this
project as new work layered onto an existing multi-tenant platform
(`tenori-labs/medai-multitenant`) — its OCR service, patient/prescription
records, scheduler, dashboard, consent gating, and Exotel telephony. None
of that lives here; this repo is the CALL-E integration layer, built and
tested standalone with an in-memory store and fixture OCR data.

Before the Devpost submission, the team needs to either (a) merge this
into `medai-multitenant` and wire it to the real OCR service and database,
or (b) be explicit in the submission that this repo is the new,
free-standing layer and the platform underneath is a separate, pre-
existing codebase. Don't let the submission read as if this repo alone
were pre-existing — it isn't; every file here was written during the
hackathon.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in CALLE_API_KEY and TEST_PHONE
```

## Running the tests

```
python -m pytest tests/ -q
```

## Running the demo

```
uvicorn app:app --reload
python demo_call.py demo-clean --dry-run
```

See `DEMO.md` for the full recording runbook (beats, commands, what to
say when).

## Structure

```
app.py                    FastAPI entrypoint — webhook receiver, demo endpoints, dashboard
demo_call.py               CLI: preview a task locally, or place a real call
medai_readback/
  readback.py               Readback task prompt + result schema (PRD A1-A6)
  confirmations.py          Pending-confirmation store + outcome routing (PRD S3, S4)
  webhooks.py                CALL-E webhook receiver, deduped, no polling (PRD B3)
  calle.py                   CALL-E API adapter (PRD B1, B2, B5)
  provider.py                 Config-selectable provider — CALL-E live, Exotel stubbed (PRD G3)
  locale_support.py           Never guess a language (PRD A3)
  adherence.py, escalation.py Ported call taxonomies (Workstream B)
  dashboard.py                 Correction-review HTML surface (PRD G2)
  store.py                     In-memory Motor/PyMongo stand-in for the demo
ocr/main.py                Fixture-backed OCR extraction (PRD section 11 mitigation)
skills/prescription-readback/  Standalone community package (PRD G4)
tests/                     41 original + 57 added this session
test_readback_call.py, test_readback_api.py, src/  Early SDK exploration —
  superseded by app.py + demo_call.py, kept for reference
```

## Safety rules (PRD section 7 — non-negotiable)

- Identity confirmed before any medication name is spoken.
- Nothing on voicemail beyond a callback request.
- Nothing schedules on any outcome but a reached, fully-confirmed call.
- Corrections are captured verbatim and handed to a human — never
  auto-applied.
- A language without a verified support test never gets a call.

## Known gaps

- **CALL-E's actual language support hasn't been tested against the live
  API.** This was the PRD's own Day-1 gating risk. `locale_support.py`
  defaults to `en-IN` only until someone runs that test — do it before
  recording anything in another language.
- **Exotel is a stub**, not a real integration (`provider.py`'s
  `ExotelProviderNotConfigured`) — the real `exotel.py` lives in
  `medai-multitenant`, which this repo doesn't have access to.
- **OCR is fixture-backed**, not a live model — `ocr/main.py` returns
  pre-extracted sample scans, matching the PRD's own risk mitigation for
  judge reproducibility, not a real handwriting-OCR pipeline.
- **No live phone verification of any of the above** — everything here is
  tested with mocked HTTP calls; placing a real call still needs a real
  `CALLE_API_KEY` and a human to answer.
