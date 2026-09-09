"""Telephony provider selection — PRD G3.

"CALL-E runs as a first-class telephony provider alongside Exotel...
dispatchable via either provider by config." CalleService (calle.py)
already mirrors the shape this needs (call / get_call_details). Exotel's
real implementation lives in agent/services/exotel.py in
tenori-labs/medai-multitenant, which this repo doesn't have access to —
ExotelProviderNotConfigured below is a deliberate stub, not a working
integration. Port the real exotel.py in before selecting "exotel" for
anything but a config/wiring test.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol

from medai_readback.calle import CalleService


class TelephonyProvider(Protocol):
    async def call(
        self,
        to_number: str,
        task: str,
        result_schema: dict,
        metadata: dict,
        webhook_url: Optional[str] = None,
        region: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> dict: ...

    async def get_call_details(self, call_sid: str) -> dict: ...


class ExotelProviderNotConfigured:
    """Stands in for the real ExotelService until it's ported in. Every
    method fails loudly rather than silently pretending to place a call."""

    async def call(self, *args, **kwargs) -> dict:
        raise NotImplementedError(
            "TELEPHONY_PROVIDER=exotel was selected but no real ExotelService "
            "is wired in here — this repo only has CALL-E. Port "
            "agent/services/exotel.py from tenori-labs/medai-multitenant into "
            "medai_readback/, or set TELEPHONY_PROVIDER=calle."
        )

    async def get_call_details(self, call_sid: str) -> dict:
        raise NotImplementedError(
            "TELEPHONY_PROVIDER=exotel was selected but not wired in — see call() for details."
        )


_PROVIDERS = frozenset({"calle", "exotel"})


async def get_provider(name: Optional[str] = None) -> TelephonyProvider:
    """Return the configured telephony provider. Defaults to CALL-E.

    `name` overrides TELEPHONY_PROVIDER for one call; leave it unset to use
    the process-wide config.
    """
    selected = (name or os.getenv("TELEPHONY_PROVIDER", "calle")).strip().lower()
    if selected not in _PROVIDERS:
        raise ValueError(
            f"Unknown TELEPHONY_PROVIDER={selected!r}; expected one of {sorted(_PROVIDERS)}"
        )
    if selected == "exotel":
        return ExotelProviderNotConfigured()
    return await CalleService.get_instance()
