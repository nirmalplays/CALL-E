# Demo recording runbook

Covers what's actually built right now: the readback call, a live correction,
and the review-queue outcome. It does **not** cover the adherence call or
caregiver escalation from the original PRD section 8 script — those haven't
been ported to CALL-E yet (Workstream B), so don't promise them on camera
until that lands. Cut the recording at ~2:10 until then, or coordinate with
whoever owns that piece first.

## Before recording

1. `pip install -r requirements.txt`
2. `cp .env.example .env` — fill in `CALLE_API_KEY` and a real `TEST_PHONE`
   you can pick up on camera.
3. Optional but recommended — a real webhook instead of eyeballing the
   in-memory store: tunnel the app (`ngrok http 8000`), set
   `CALLE_WEBHOOK_URL` in `.env` to `<tunnel>/calle/webhook`.
4. Start the server: `uvicorn app:app --reload`
5. Dry-run both fixtures once — no call placed, just checks the script reads
   naturally:
   ```
   python demo_call.py demo-clean --dry-run
   python demo_call.py demo-misread-dose --dry-run
   ```

## Beats

**0:00–0:20 — Problem.** Hold up a real (or realistic) handwritten
prescription. Say plainly that the patient can't read it.

**0:20–0:40 — Scan.** Cut to `python demo_call.py demo-misread-dose --dry-run`
on screen. The extracted regimen prints — including "Metformin, 5mg", the
fixture's built-in misread. State that OCR is not ground truth.

**0:40–1:40 — Phone rings.** Run:
```
python demo_call.py demo-misread-dose --phone +91XXXXXXXXXX
```
Answer, confirm identity, and when the call reads back "Metformin, 5mg,"
correct it out loud — "it's actually 50mg." Confirm the rest of the call
normally.

**1:40–2:10 — Correction lands in review.** Once the webhook resolves the
call, hit the queue on screen:
```
curl localhost:8000/demo/confirmations
```
Point out: status is `"review"`, the correction is stored word-for-word in
`correction_text`, nothing was scheduled.

**Optional, if you also want to show the clean path:**
```
python demo_call.py demo-clean --phone +91XXXXXXXXXX
```
Confirm everything on the call, check `/demo/confirmations` again — this one
resolves `"scheduled"`.

**Close.** State what was new during the hackathon: the readback call, the
CALL-E adapter, the correction routing — not the OCR (fixture-backed for
this demo, see `ocr/main.py`), not the MedAI platform underneath.

## Known gaps to mention or avoid promising on camera

- No live OCR model — `ocr/main.py` is fixture-backed by design (PRD section
  11 risk mitigation), not a real scan of the prescription you hold up.
- No adherence call or escalation yet — don't cut to "already took it" or a
  caregiver escalation, that path isn't built.
- No dashboard UI — `/demo/confirmations` is a raw JSON queue, not the
  correction-review surface from PRD G2.
