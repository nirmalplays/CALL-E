import pytest

from medai_readback.locale_support import resolve_locale, supported_locales


def test_default_supported_locales_is_english_only():
    """CALL-E's actual language support hasn't been verified yet (PRD section
    11, Critical risk) — until it is, nothing but en-IN should be trusted."""
    assert supported_locales() == {"en-IN"}


def test_resolve_locale_returns_supported_locale_unchanged():
    assert resolve_locale("en-IN") == "en-IN"


def test_resolve_locale_falls_back_on_unsupported_language():
    assert resolve_locale("hi-IN") is None


def test_resolve_locale_falls_back_on_empty_language():
    assert resolve_locale("") is None


def test_supported_locales_respects_env_override(monkeypatch):
    monkeypatch.setenv("CALLE_SUPPORTED_LOCALES", "en-IN, hi-IN,ta-IN")
    assert supported_locales() == {"en-IN", "hi-IN", "ta-IN"}
    assert resolve_locale("hi-IN") == "hi-IN"


def test_supported_locales_ignores_blank_env_var(monkeypatch):
    monkeypatch.setenv("CALLE_SUPPORTED_LOCALES", "")
    assert supported_locales() == {"en-IN"}
