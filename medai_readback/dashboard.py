"""Correction-review dashboard — PRD G2.

"Corrections captured from the call are routed to staff, not silently
applied" (G2). This renders the pending_confirmations queue as plain HTML —
grouped so a coordinator sees what needs a decision (review, fallback)
before what's already resolved (scheduled) — with no JS and no build step,
since the point is a surface staff can open, not a frontend project.

A pure string-in, string-out function so it's testable without a running
server; app.py wires it to the real store.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List

# Needs attention first: nothing has been scheduled for these yet.
_STATUS_ORDER = ["review", "fallback", "pending", "scheduled"]

_STATUS_LABELS = {
    "review": "Needs review — patient corrected something",
    "fallback": "Needs review — call did not resolve cleanly",
    "pending": "Call placed, awaiting outcome",
    "scheduled": "Confirmed and scheduled",
}


def _mask_phone(phone: str) -> str:
    """Show enough to recognize a number, not enough to dial it from a screenshot."""
    digits = phone.strip()
    if len(digits) <= 4:
        return digits
    return digits[:3] + "•" * (len(digits) - 6) + digits[-3:]


def _medication_rows(medications: List[Dict[str, Any]], corrections: List[Dict[str, Any]]) -> str:
    correction_by_name = {c.get("name_as_read"): c for c in corrections}
    rows = []
    for med in medications:
        name = html.escape(med.get("name", "unnamed"))
        correction = correction_by_name.get(name)
        if correction:
            status = html.escape(correction.get("status", ""))
            note = html.escape(correction.get("correction_text") or "")
            rows.append(
                f'<li class="med corrected"><b>{name}</b> — {status}'
                f'<div class="correction-text">&ldquo;{note}&rdquo;</div></li>'
            )
        else:
            dosage = html.escape(med.get("dosage", ""))
            rows.append(f'<li class="med">{name} {dosage}</li>')
    return "\n".join(rows)


def _confirmation_card(doc: Dict[str, Any]) -> str:
    patient_name = html.escape(doc.get("patient_name", "Unknown"))
    phone = html.escape(_mask_phone(doc.get("phone_number", "")))
    call_id = html.escape(doc.get("call_id", ""))
    status = doc.get("status", "pending")
    corrections = doc.get("corrections", []) or []
    meds_html = _medication_rows(doc.get("medications", []), corrections)
    notes = doc.get("structured_result", {}).get("patient_notes") if doc.get("structured_result") else None
    notes_html = f'<p class="notes">Patient note: &ldquo;{html.escape(notes)}&rdquo;</p>' if notes else ""

    return f"""
    <article class="card status-{html.escape(status)}">
      <header>
        <h3>{patient_name}</h3>
        <span class="phone">{phone}</span>
        <span class="call-id">{call_id}</span>
      </header>
      <ul class="meds">{meds_html}</ul>
      {notes_html}
    </article>
    """


def render_dashboard(confirmations: List[Dict[str, Any]]) -> str:
    grouped: Dict[str, List[Dict[str, Any]]] = {status: [] for status in _STATUS_ORDER}
    for doc in confirmations:
        grouped.setdefault(doc.get("status", "pending"), []).append(doc)

    sections = []
    for status in _STATUS_ORDER:
        docs = grouped.get(status, [])
        label = _STATUS_LABELS.get(status, status)
        cards = "\n".join(_confirmation_card(d) for d in docs) or '<p class="empty">Nothing here.</p>'
        sections.append(
            f'<section><h2>{html.escape(label)} <span class="count">{len(docs)}</span></h2>{cards}</section>'
        )

    body = "\n".join(sections)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>MedAI — Prescription confirmations</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; background: #f4f6f5; color: #10201c; margin: 0; padding: 2rem; }}
  h1 {{ margin: 0 0 1.5rem; }}
  section {{ margin-bottom: 2rem; }}
  h2 {{ font-size: 1.05rem; border-bottom: 1px solid #d7ddd7; padding-bottom: .4rem; }}
  .count {{ color: #7c8b83; font-weight: normal; }}
  .card {{ background: #fff; border: 1px solid #d7ddd7; border-left: 4px solid #7c8b83; border-radius: 4px;
           padding: .9rem 1.1rem; margin-bottom: .7rem; }}
  .status-review, .status-fallback {{ border-left-color: #b5730f; }}
  .status-scheduled {{ border-left-color: #1f7a5c; }}
  header {{ display: flex; align-items: baseline; gap: .7rem; margin-bottom: .5rem; }}
  header h3 {{ margin: 0; font-size: 1rem; }}
  .phone, .call-id {{ font-family: monospace; font-size: .8rem; color: #7c8b83; }}
  .meds {{ list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .35rem; }}
  .med {{ font-size: .92rem; }}
  .med.corrected {{ color: #b5730f; }}
  .correction-text {{ font-size: .85rem; color: #4c5d55; margin-top: .1rem; }}
  .notes {{ font-size: .85rem; color: #4c5d55; font-style: italic; }}
  .empty {{ color: #7c8b83; font-size: .9rem; }}
</style>
</head>
<body>
<h1>Prescription confirmations</h1>
{body}
</body>
</html>"""
