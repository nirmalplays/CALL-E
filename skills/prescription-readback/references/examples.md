# Worked examples

Phone numbers below are masked. None of these were real calls.

## Confirmed path

**Record extracted:**
```json
[{"name": "Metformin", "dosage": "500mg", "quantity": "1",
  "schedule": ["MORNING", "EVENING"], "duration": "30 days",
  "instructions": "after food"}]
```

**Call, paraphrased:**
> "Hello, this is MedAI calling for Demo Patient. Am I speaking with the
> patient who visited the doctor?"
> — "Yes, speaking."
> "Thank you. We scanned your prescription and want to read it back...
> Medication 1: Metformin, 500mg, take 1 tablet in the morning and
> evening, for 30 days, after food. Is this correct?"
> — "Yes, that's right."
> "Thank you for confirming. We will set up your medication reminders
> now."

**Result:**
```json
{"reached_patient": "yes", "overall": "confirmed",
 "medications": [{"name_as_read": "Metformin", "status": "confirmed"}]}
```

**Disposition:** `decide(result, original_medications) == "scheduled"` — permits downstream handoff; scheduling still needs to succeed.

## Corrected path

**Same record, but the extraction misread the dose** (5mg instead of the
actual 50mg — a single-digit OCR error on handwriting):

**Call, paraphrased:**
> "...Medication 1: Metformin, 5mg, take 1 tablet in the morning and
> evening... Is this correct?"
> — "No, it's actually 50 milligrams, not 5."
> "Thank you, I have noted that. Our team will review your corrections
> before updating your records — nothing changes without staff
> verification."

**Result:**
```json
{"reached_patient": "yes", "overall": "corrected",
 "medications": [{"name_as_read": "Metformin", "status": "corrected",
                   "correction_text": "it's actually 50 milligrams, not 5"}]}
```

**Disposition:** `decide(result) == "review"` — nothing is scheduled;
the correction, verbatim, goes to a human queue.

## Wrong person answers

**Call, paraphrased:**
> "Hello, this is MedAI calling for Demo Patient. Am I speaking with the
> patient who visited the doctor?"
> — "No, this is their son, they're not home."
> "No problem. Could you please ask them to call us back? Thank you."
> *(call ends — no medication name was ever said)*

**Result:**
```json
{"reached_patient": "wrong_person", "overall": "unclear", "medications": []}
```

**Disposition:** `decide(result) == "fallback"` — routes to dashboard
staff review, retried per your own retry policy.

## Duplicate webhook delivery

CALL-E (like most webhook senders) can retry a delivery. The same
`call.completed` event, same event id, arriving twice must not double-run
whatever `on_result` does (e.g. scheduling reminders twice).

```python
seen = set()
first = handle_calle_event("evt_123", payload, seen, on_result)   # {"status": "processed", ...}
second = handle_calle_event("evt_123", payload, seen, on_result)  # {"status": "duplicate"}
```

`on_result` only ran once.
