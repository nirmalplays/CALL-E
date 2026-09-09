import pytest

from medai_readback.calle import CalleService
from medai_readback.provider import ExotelProviderNotConfigured, get_provider


@pytest.mark.asyncio
async def test_default_provider_is_calle(monkeypatch):
    monkeypatch.delenv("TELEPHONY_PROVIDER", raising=False)
    provider = await get_provider()
    assert isinstance(provider, CalleService)


@pytest.mark.asyncio
async def test_env_var_selects_calle_explicitly(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER", "calle")
    provider = await get_provider()
    assert isinstance(provider, CalleService)


@pytest.mark.asyncio
async def test_env_var_selects_exotel_stub(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER", "exotel")
    provider = await get_provider()
    assert isinstance(provider, ExotelProviderNotConfigured)


@pytest.mark.asyncio
async def test_explicit_name_overrides_env_var(monkeypatch):
    monkeypatch.setenv("TELEPHONY_PROVIDER", "exotel")
    provider = await get_provider("calle")
    assert isinstance(provider, CalleService)


@pytest.mark.asyncio
async def test_unknown_provider_name_raises():
    with pytest.raises(ValueError, match="Unknown TELEPHONY_PROVIDER"):
        await get_provider("carrier-pigeon")


@pytest.mark.asyncio
async def test_exotel_stub_fails_loudly_instead_of_pretending_to_call():
    provider = ExotelProviderNotConfigured()
    with pytest.raises(NotImplementedError, match="no real ExotelService is wired in"):
        await provider.call(
            to_number="+919876543210", task="t", result_schema={}, metadata={"call_id": "x"},
        )


@pytest.mark.asyncio
async def test_exotel_stub_get_call_details_also_fails_loudly():
    provider = ExotelProviderNotConfigured()
    with pytest.raises(NotImplementedError):
        await provider.get_call_details("some_sid")
