# Safety reasoning

Each rule below exists because of a specific failure mode, not as a
generic best practice. Know the failure before you relax the rule.

## Identity before disclosure

**Failure it prevents:** a shared household phone, a different family
member answering, or a wrong number gets someone else's medical
information read to them.

**Rule:** the call confirms it is speaking with the actual patient before
any record detail is mentioned. If identity can't be confirmed, the call
asks for a callback and ends — it never "plays it safe" by being vague
about the medication, because a vague-but-present mention is still a
disclosure.

## Nothing on voicemail

**Failure it prevents:** voicemail is not a private channel — anyone with
access to the phone or the carrier's voicemail system can hear it, often
without a PIN. A medication list left on voicemail is a disclosure with no
identity check at all.

**Rule:** a voicemail greeting gets a generic callback request only.

## Corrections are never auto-applied

**Failure it prevents:** an automated speech-to-structured pipeline is not
perfect. A misheard "not" or a mistranscribed number, applied directly to
a source record, silently corrupts data that downstream systems will then
treat as verified. The correction call was supposed to catch an error —
auto-applying its output uncritically just moves the error one step
downstream and makes it harder to find.

**Rule:** `decide()` only reaches a "proceed" disposition when the patient
was reached AND every item was confirmed as-read. Any correction, however
small, routes to a human with the correction captured verbatim (in the
patient's own words, not a paraphrase) — the human sees exactly what was
said and decides what to do with it.

## A "confirmed" result requires an actual reached patient

**Failure it prevents:** a structured-extraction model can return
`overall: confirmed` while `reached_patient: no` — for example, if it
mis-scores a call that never connected. Trusting the `overall` field alone
would proceed on a call that never actually happened.

**Rule:** `decide()` checks both fields. `reached_patient != "yes"` always
falls back, regardless of what `overall` says.

## Overflow routes to a human

**Failure it prevents:** a long call is unreliable — attention drifts,
audio degrades, and the later items in a long list get less careful
verification than the earlier ones. Forcing a long record through the
same call quality bar as a short one produces false confidence on the
items nobody was really listening for by the end.

**Rule:** a hard cap (`MAX_READBACK_MEDICATIONS`) rejects long records
outright rather than attempting a degraded call.

## Language is never guessed

**Failure it prevents:** placing a call in a language the underlying
voice model has not actually been verified to handle conversationally
produces a call that sounds like it worked (a transcript, a structured
result) while actually just being wrong — the patient may have
misunderstood most of it, and nothing in the output signals that.

**Rule:** resolve the patient's language preference against a list of
languages you have actually tested, not a list of languages you assume
the provider supports. Anything not on that list falls back to a human,
logged. Never place the call anyway "because it's probably fine."


## Complete medication reconciliation

Pass the trusted pending medication list to `decide(result, expected_medications)`.
Every original medication must appear exactly once with status confirmed and no
correction text. Missing context, malformed entries, unknown names, duplicate
names, and unsure entries fall back to staff. Duplicate original names are also
ambiguous until stable medication IDs are introduced. Spoken corrections route
to review even when the overall result incorrectly claims confirmation.
Failed and result-validation-failed events cannot approve a regimen.
