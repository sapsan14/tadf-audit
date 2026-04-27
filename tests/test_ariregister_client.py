"""Ariregister public-API client tests."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from tadf.external.ariregister_client import (
    CompanyHit,
    is_available,
    lookup_company,
    search_company,
)

_TADF_ROW = {
    "company_id": 9000098221,
    "reg_code": 12503172,
    "name": "TADF Ehitus OÜ",
    "historical_names": [],
    "status": "R",
    "legal_address": "Ida-Viru maakond, Narva-Jõesuu linn, E. Vilde tn 8",
    "zip_code": "29022",
    "legal_form": "5",
    "url": "https://ariregister.rik.ee/est/company/12503172/TADF-Ehitus-OÜ",
}

_TALSAD_ROW = {
    "company_id": 2000004900,
    "reg_code": 10137319,
    "name": "aktsiaselts TALLINNA SADAM",
    "status": "R",
    "legal_address": "Harju maakond, Tallinn, Sadama tn 25",
    "zip_code": "15051",
    "legal_form": "1",
    "url": "https://ariregister.rik.ee/est/company/10137319/aktsiaselts-TALLINNA-SADAM",
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
    # Also ensure tier-3 creds aren't accidentally inherited from CI.
    monkeypatch.delenv("ARIREGISTER_USERNAME", raising=False)
    monkeypatch.delenv("ARIREGISTER_PASSWORD", raising=False)


def test_is_available_always_true() -> None:
    assert is_available() is True


def test_search_short_input_skips_network() -> None:
    with patch("httpx.Client.get") as mock_get:
        assert search_company("") == []
        assert search_company(" ") == []
        assert search_company("t") == []
    mock_get.assert_not_called()


def test_search_parses_autocomplete_row() -> None:
    def fake_get(self, url, **kwargs):
        assert url.endswith("/autocomplete")
        params = kwargs.get("params") or {}
        assert params.get("q") == "tadf"
        return _MockResponse({"status": "OK", "data": [_TADF_ROW]})

    with patch("httpx.Client.get", new=fake_get):
        hits = search_company("tadf")

    assert len(hits) == 1
    h = hits[0]
    assert isinstance(h, CompanyHit)
    assert h.reg_code == "12503172"
    assert h.name == "TADF Ehitus OÜ"
    assert h.legal_form == "OÜ"
    assert h.legal_form_code == "5"
    assert h.status == "R"
    assert h.status_label == "активна"
    assert h.address and "Vilde" in h.address


def test_search_handles_unknown_legal_form_code() -> None:
    """An unmapped legal_form falls through to the raw code, not None.

    Better to surface a number we don't translate yet than to lie about
    the corporate structure.
    """
    odd_row = {**_TADF_ROW, "legal_form": "999"}

    def fake_get(self, url, **kwargs):
        return _MockResponse({"status": "OK", "data": [odd_row]})

    with patch("httpx.Client.get", new=fake_get):
        hits = search_company("anything")

    assert hits[0].legal_form == "999"
    assert hits[0].legal_form_code == "999"


def test_search_caches() -> None:
    call_count = 0

    def fake_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _MockResponse({"status": "OK", "data": [_TADF_ROW]})

    with patch("httpx.Client.get", new=fake_get):
        a = search_company("tadf")
        b = search_company("tadf")

    assert a == b
    assert call_count == 1


def test_search_status_not_ok_returns_empty() -> None:
    def fake_get(self, url, **kwargs):
        return _MockResponse({"status": "ERROR", "data": []})

    with patch("httpx.Client.get", new=fake_get):
        hits = search_company("anything")

    assert hits == []


def test_search_handles_network_error() -> None:
    def fake_get(self, url, **kwargs):
        raise httpx.ConnectError("offline")

    with patch("httpx.Client.get", new=fake_get):
        hits = search_company("tadf")

    assert hits == []


def test_lookup_by_reg_code_returns_client_fields() -> None:
    def fake_get(self, url, **kwargs):
        params = kwargs.get("params") or {}
        assert params.get("q") == "12503172"
        return _MockResponse({"status": "OK", "data": [_TADF_ROW]})

    with patch("httpx.Client.get", new=fake_get):
        fields = lookup_company("12503172")

    assert fields is not None
    assert fields["name"] == "TADF Ehitus OÜ"
    assert fields["reg_code"] == "12503172"
    assert "Vilde" in (fields.get("address") or "")
    assert fields["legal_form"] == "OÜ"
    assert fields["status"] == "R"


def test_lookup_invalid_reg_code_returns_none() -> None:
    assert lookup_company("") is None
    assert lookup_company("abcdefgh") is None
    assert lookup_company("123") is None  # too short
    assert lookup_company("123456789") is None  # too long


def test_lookup_caches() -> None:
    call_count = 0

    def fake_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _MockResponse({"status": "OK", "data": [_TADF_ROW]})

    with patch("httpx.Client.get", new=fake_get):
        a = lookup_company("12503172")
        b = lookup_company("12503172")

    assert a == b
    assert call_count == 1


def test_lookup_force_refresh_bypasses_cache() -> None:
    call_count = 0

    def fake_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _MockResponse({"status": "OK", "data": [_TADF_ROW]})

    with patch("httpx.Client.get", new=fake_get):
        lookup_company("12503172")
        lookup_company("12503172", force_refresh=True)

    assert call_count == 2


def test_lookup_returns_none_on_empty_data() -> None:
    def fake_get(self, url, **kwargs):
        return _MockResponse({"status": "OK", "data": []})

    with patch("httpx.Client.get", new=fake_get):
        assert lookup_company("99999998") is None


def test_search_filters_malformed_rows() -> None:
    def fake_get(self, url, **kwargs):
        return _MockResponse(
            {"status": "OK", "data": [_TADF_ROW, {"reg_code": None}, "not a dict"]}
        )

    with patch("httpx.Client.get", new=fake_get):
        hits = search_company("tadf")

    assert len(hits) == 1
    assert hits[0].name == "TADF Ehitus OÜ"


def test_search_limit_slices_response() -> None:
    payload = {"status": "OK", "data": [_TADF_ROW, _TALSAD_ROW]}

    def fake_get(self, url, **kwargs):
        return _MockResponse(payload)

    with patch("httpx.Client.get", new=fake_get):
        hits = search_company("aktsia", limit=1)

    assert len(hits) == 1
