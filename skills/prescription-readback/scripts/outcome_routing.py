"""Outcome routing — maps a readback result onto a disposition.

No framework or database dependency. See ../references/safety.md for why
`decide()` requires both fields rather than trusting `overall` alone.
"""

from __future__ import annotations

from typing import Any, Dict


def decide(structured: Dict[str, Any], expected_medications=None) -> str:
    """Approve only a complete, unambiguous match to the pending regimen.

    The expected medication list must come from trusted pending state, never
    from the returned call result. Missing context fails closed. Duplicate
    names are ambiguous without medication IDs and require staff review.
    """
    if not isinstance(structured, dict) or structured.get("reached_patient") != "yes":
        return "fallback"
    overall = structured.get("overall")
    medications = structured.get("medications")
    if overall == "corrected":
        return "review"
    if not isinstance(medications, list) or not medications:
        return "fallback"
    if any(not isinstance(m, dict) for m in medications):
        return "fallback"
    # A correction takes precedence even when the overall summary contradicts it.
    if any(m.get("status") == "corrected" or
           (isinstance(m.get("correction_text"), str) and m["correction_text"].strip())
           for m in medications):
        return "review"
    if overall != "confirmed":
        return "fallback"
    if any(m.get("status") != "confirmed" or
           m.get("correction_text") not in (None, "") for m in medications):
        return "fallback"
    if not isinstance(expected_medications, list) or not expected_medications:
        return "fallback"

    def names(items, key):
        result = []
        for item in items:
            if not isinstance(item, dict):
                return None
            name = item.get(key)
            if not isinstance(name, str) or not name.strip():
                return None
            result.append(" ".join(name.split()).casefold())
        return result

    expected = names(expected_medications, "name")
    actual = names(medications, "name_as_read")
    if not expected or not actual:
        return "fallback"
    if len(set(expected)) != len(expected) or len(set(actual)) != len(actual):
        return "fallback"
    if sorted(expected) != sorted(actual):
        return "fallback"
    return "scheduled"
