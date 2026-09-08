"""Tiny .env loader shared by the test scripts (no python-dotenv dependency).

Reads .env into os.environ (without overwriting anything already set in the
real environment) and exposes the CALL-E + test-phone config as constants.
Import this before reading os.environ in any script that needs these values.
"""
import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent / ".env"

if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        os.environ.setdefault(key, value)

API_KEY = os.environ.get("CALLE_API_KEY")
BASE_URL = os.environ.get("CALLE_BASE_URL", "https://api.heycall-e.com")
TEST_PHONE = os.environ.get("TEST_PHONE")
TEST_REGION = os.environ.get("TEST_REGION", "IN")
TEST_LOCALE = os.environ.get("TEST_LOCALE", "en-IN")


def require(name: str, value):
    if not value:
        raise SystemExit(
            f"Error: {name} is not set. Copy .env.example to .env and fill it in."
        )
    return value
