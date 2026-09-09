"""Outcome routing — maps a readback result onto a disposition.

No framework or database dependency. See ../references/safety.md for why
`decide()` requires both fields rather than trusting `overall` alone.
"""

from __future__ import annotations

from typing import Any, Dict


def decide(structured: Dict[str, Any]) -> str:
    """Map a structured readback result onto a disposition.

    Handing anything downstream requires BOTH that the person was reached
    and that the overall outcome is 'confirmed'. Any other combination
    falls back to human review — including a model that returns
    'confirmed' while reporting it never reached the person.
    """
    reached = structured.get("reached_patient")
    overall = structured.get("overall")

    if reached != "yes":
        return "fallback"
    if overall == "confirmed":
        return "scheduled"
    if overall == "corrected":
        return "review"
    return "fallback"
