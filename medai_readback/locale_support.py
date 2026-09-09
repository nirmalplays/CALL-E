"""Locale support for the readback call — PRD A3 and the section 11 Critical risk.

CALL-E's actual set of conversational Indian languages has not been verified
against the live API yet — that was the PRD's Day-1 task and it's still
outstanding. Until someone runs that test, only en-IN is treated as
supported; every other language_preference falls back to dashboard staff
review rather than guessing. Once verified, set CALLE_SUPPORTED_LOCALES
(comma-separated, e.g. "en-IN,hi-IN,ta-IN") — do not just add languages here
without testing them.
"""

from __future__ import annotations

import os
from typing import Optional, Set

_DEFAULT_SUPPORTED = frozenset({"en-IN"})


def supported_locales() -> Set[str]:
    raw = os.getenv("CALLE_SUPPORTED_LOCALES", "")
    configured = {loc.strip() for loc in raw.split(",") if loc.strip()}
    return configured or set(_DEFAULT_SUPPORTED)


def resolve_locale(language_preference: str) -> Optional[str]:
    """Return the locale to place the call in, or None if unsupported.

    None means: do not place the call. Fall back to dashboard staff review
    and log it — never place a call in a language the patient did not
    choose (PRD A3).
    """
    if not language_preference:
        return None
    if language_preference in supported_locales():
        return language_preference
    return None
