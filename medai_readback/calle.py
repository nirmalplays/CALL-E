"""
CALL-E Service - Singleton with managed aiohttp session.

Mirrors the ExotelService interface (call / get_call_details) so the scheduler
can dispatch through either provider without branching on response shape.

Environment:
  CALLE_API_KEY   required
  CALLE_BASE_URL  default https://api.heycall-e.com
  CALLE_REGION    default IN
  CALLE_LOCALE    default en-IN
"""

import asyncio
import os
from typing import Optional

import aiohttp
from loguru import logger

_CALLE_API_KEY = lambda: os.getenv("CALLE_API_KEY", "")
_CALLE_BASE_URL = lambda: os.getenv("CALLE_BASE_URL", "https://api.heycall-e.com")
_CALLE_REGION = lambda: os.getenv("CALLE_REGION", "IN")
_CALLE_LOCALE = lambda: os.getenv("CALLE_LOCALE", "en-IN")

# CALL-E call statuses: queued, in_progress, completed, failed, canceled
_TERMINAL_STATUSES = frozenset(["completed", "failed", "canceled"])


class CalleService:
    """Singleton CALL-E API client with a managed aiohttp session."""

    _instance: Optional["CalleService"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    @classmethod
    async def get_instance(cls) -> "CalleService":
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance._init_session()
        return cls._instance

    async def _init_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=aiohttp.TCPConnector(
                    limit=20,
                    limit_per_host=10,
                    # aiohttp defaults to aiodns (pycares) for DNS when it's
                    # installed. On Windows, pycares frequently fails to pick
                    # up the system's configured DNS servers ("Could not
                    # contact DNS servers") even though the OS resolver
                    # works fine — ThreadedResolver uses socket.getaddrinfo,
                    # the same resolver curl/nslookup use, sidestepping that.
                    resolver=aiohttp.resolver.ThreadedResolver(),
                ),
            )
            logger.info("CalleService session initialized")

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            await self._init_session()

    def _headers(self) -> dict:
        key = _CALLE_API_KEY()
        if not key:
            raise ValueError("Missing CALL-E credentials: CALLE_API_KEY")
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    # ── Public API ────────────────────────────────────────────────────────────

    async def call(
        self,
        to_number: str,
        task: str,
        result_schema: dict,
        metadata: dict,
        webhook_url: Optional[str] = None,
        region: Optional[str] = None,
        locale: Optional[str] = None,
    ) -> dict:
        """
        Place an outbound call via CALL-E's Create Call API.

        Args:
            to_number:     Recipient phone number in E.164 format.
            task:          Natural-language instruction for the call.
            result_schema: JSON Schema for structured extraction.
            metadata:      Correlation data echoed back on the webhook.
                           MUST contain "call_id".
            webhook_url:   Optional HTTPS URL for terminal call events.
            region:        Overrides CALLE_REGION for this call.
            locale:        Overrides CALLE_LOCALE for this call — callers that
                            place calls in a patient's language_preference
                            (PRD A3) should resolve it against CALL-E's
                            supported locales first and pass the result here,
                            rather than relying on the process-wide default.

        Returns:
            {"status": "call_initiated", "call_sid": "<calle call_id>"}
        """
        if os.getenv("CALLE_ENABLE_LIVE_CALLS") != "true":
            raise ValueError("Live calls disabled; explicit enablement required")
        headers = self._headers()
        if not isinstance(metadata.get("call_id"), str) or not metadata["call_id"]:
            raise ValueError("metadata.call_id is required")
        headers["Idempotency-Key"] = metadata["call_id"]
        await self._ensure_session()

        payload = {
            "task": task,
            "recipients": [
                {
                    "phones": [to_number],
                    "region": region or _CALLE_REGION(),
                    "locale": locale or _CALLE_LOCALE(),
                }
            ],
            "result_schema": result_schema,
            "metadata": metadata,
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url

        url = f"{_CALLE_BASE_URL()}/v1/calls"
        async with self._session.post(url, json=payload, headers=headers) as resp:
            # POST /v1/calls is a create endpoint — CALL-E returns 201, not
            # 200. Confirmed against the live API (verified 2026-09-09):
            # treating 201 as an error meant every successful call placement
            # was reported as a crash.
            if resp.status not in (200, 201):
                error = await resp.text()
                raise Exception(f"CALL-E API error ({resp.status}): {error}")
            body = await resp.json()

        # The live API returns the call's id as "id", not "call_id" — same
        # field GET /v1/calls/{id} echoes back. Confirmed against a real
        # call (call_Ljdf6v_p6TrKK3YAoniMEg); "call_id" doesn't exist on the
        # response at all, so this previously always fell through to
        # "unknown" and silently broke correlation.
        call_sid = body.get("id")
        if not isinstance(call_sid, str) or not call_sid:
            raise RuntimeError("CALL-E accepted request without a call ID; reconcile before retrying")
        logger.info("CALL-E call initiated: id={}", call_sid)
        return {"status": "call_initiated", "call_sid": call_sid}

    async def get_call_details(self, call_sid: str) -> dict:
        """
        Fetch call state from CALL-E's Get Call API.

        Returns:
            {"status": str, "state": "terminal"|"active", "call_details": dict}
        """
        headers = self._headers()
        await self._ensure_session()

        url = f"{_CALLE_BASE_URL()}/v1/calls/{call_sid}"
        try:
            async with self._session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    raise Exception("CALL-E API authentication failed (401)")
                if resp.status != 200:
                    error = await resp.text()
                    raise Exception(f"CALL-E API error ({resp.status}): {error}")
                result = await resp.json()
        except aiohttp.ClientError as exc:
            raise Exception(f"Network error calling CALL-E API: {exc}") from exc

        status = result.get("status", "unknown")
        state = "terminal" if status in _TERMINAL_STATUSES else "active"
        return {"status": status, "state": state, "call_details": result}

    async def health_check(self) -> dict:
        return {
            "session_active": self._session is not None
            and not self._session.closed,
            "api_key_set": bool(_CALLE_API_KEY()),
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        logger.info("CalleService session closed")

    @classmethod
    async def shutdown(cls):
        if cls._instance:
            await cls._instance.close()
            cls._instance = None
