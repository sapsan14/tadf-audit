"""In-ADS (Maa-amet) gazetteer client tests.

Mocks the HTTP layer at httpx.Client.get so the parser, cache, and
empty-input behaviour are exercised deterministically.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from tadf.external.inaadress_client import (
    AddressHit,
    is_available,
    lookup_address,
    search_address,
)

_SAMPLE_HIT = {
    "pikkaadress": "Ida-Viru maakond, Narva-Jõesuu linn, Auga tn 8",
    "aadresstekst": "Auga tn 8",
    "adr_id": "ADS00112233",
    "tunnus": "85101:004:0020",
    "viitepunkt_x": "657734.12",
    "viitepunkt_y": "6502345.43",
}


class _MockResponse:
    def __init__(self, data, status: int = 200):
        self._data = data
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom", request=None, response=None  # type: ignore[arg-type]
            )

    def json(self):
        return self._data


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tadf.external.cache.CACHE_DIR", tmp_path)


def test_is_available_always_true() -> None:
    assert is_available() is True


def test_search_short_input_skips_network() -> None:
    with patch("httpx.Client.get") as mock_get:
        assert search_address("") == []
        assert search_address(" ") == []
        assert search_address("a") == []
    mock_get.assert_not_called()


def test_search_returns_parsed_hits() -> None:
    def fake_get(self, url, **kwargs):
        assert "gazetteer" in url
        params = kwargs.get("params") or {}
        assert params.get("address") == "Auga"
        return _MockResponse({"addresses": [_SAMPLE_HIT]})

    with patch("httpx.Client.get", new=fake_get):
        hits = search_address("Auga")

    assert len(hits) == 1
    h = hits[0]
    assert isinstance(h, AddressHit)
    assert "Auga tn 8" in h.address
    assert h.ads_id == "ADS00112233"
    assert h.kataster == "85101:004:0020"
    assert h.coords == (657734.12, 6502345.43)


def test_search_handles_alt_envelope_keys() -> None:
    """If the gazetteer ever returns `tulemused` or a bare list,
    the parser shouldn't blow up."""

    def fake_get(self, url, **kwargs):
        return _MockResponse({"tulemused": [_SAMPLE_HIT]})

    with patch("httpx.Client.get", new=fake_get):
        hits = search_address("Auga")

    assert len(hits) == 1


def test_search_skips_entries_without_address() -> None:
    bad_hit = {"adr_id": "ADS-X", "viitepunkt_x": 1, "viitepunkt_y": 2}

    def fake_get(self, url, **kwargs):
        return _MockResponse({"addresses": [bad_hit, _SAMPLE_HIT]})

    with patch("httpx.Client.get", new=fake_get):
        hits = search_address("Auga")

    assert len(hits) == 1
    assert hits[0].ads_id == "ADS00112233"


def test_search_caches() -> None:
    call_count = 0

    def fake_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _MockResponse({"addresses": [_SAMPLE_HIT]})

    with patch("httpx.Client.get", new=fake_get):
        h1 = search_address("Auga")
        h2 = search_address("Auga")

    assert h1 == h2
    assert call_count == 1


def test_search_handles_unexpected_shape() -> None:
    def fake_get(self, url, **kwargs):
        return _MockResponse({"unexpected": True})

    with patch("httpx.Client.get", new=fake_get):
        hits = search_address("Auga")

    assert hits == []


def test_search_handles_network_error() -> None:
    def fake_get(self, url, **kwargs):
        raise httpx.ConnectError("nope")

    with patch("httpx.Client.get", new=fake_get):
        hits = search_address("Auga")

    assert hits == []


def test_lookup_returns_first_match() -> None:
    def fake_get(self, url, **kwargs):
        params = kwargs.get("params") or {}
        assert params.get("adsid") == "ADS00112233"
        return _MockResponse({"addresses": [_SAMPLE_HIT]})

    with patch("httpx.Client.get", new=fake_get):
        h = lookup_address("ADS00112233")

    assert h is not None
    assert h.address.startswith("Ida-Viru")


def test_lookup_caches() -> None:
    call_count = 0

    def fake_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _MockResponse({"addresses": [_SAMPLE_HIT]})

    with patch("httpx.Client.get", new=fake_get):
        h1 = lookup_address("ADS00112233")
        h2 = lookup_address("ADS00112233")

    assert h1 == h2
    assert call_count == 1


def test_lookup_force_refresh_bypasses_cache() -> None:
    call_count = 0

    def fake_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _MockResponse({"addresses": [_SAMPLE_HIT]})

    with patch("httpx.Client.get", new=fake_get):
        lookup_address("ADS00112233")
        lookup_address("ADS00112233", force_refresh=True)

    assert call_count == 2


def test_lookup_empty_input() -> None:
    assert lookup_address("") is None
    assert lookup_address("   ") is None
