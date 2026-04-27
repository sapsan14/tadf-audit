"""Mapper tests for tadf.external.ehr_client.

The HTTP layer is tested via captured fixtures (real responses pulled
from livekluster.ehr.ee on 2026-04-27 against EHR code 102032773 +
address "Auga 8"). We only mock the network call so we exercise the
mapper deterministically without hitting prod every CI run.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from tadf.external.ehr_client import (
    lookup_ehr,
    map_building_data,
    search_ehr,
)

_FIX = Path(__file__).parent / "fixtures" / "ehr"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Mapper tests
# ---------------------------------------------------------------------------


def test_map_building_data_full() -> None:
    data = _load("buildingData_102032773.json")
    out = map_building_data(data)

    assert out["address"] == "Ida-Viru maakond, Sillamäe linn, Linna AÜ 1062"
    assert out["use_purpose"] == "Suvila, aiamaja"
    assert out["ehr_code"] == "102032773"
    assert out["kataster_no"] == "85101:004:0020"
    assert out["footprint_m2"] == 103.0
    assert out["height_m"] == 7.0
    assert out["volume_m3"] == 142.0
    assert out["storeys_above"] == 2
    assert out["construction_year"] == 1999


def test_map_building_data_handles_missing_keys() -> None:
    """Empty or partial JSON shouldn't blow up — just produces an empty dict."""
    assert map_building_data({}) == {}
    assert map_building_data({"ehitis": {}}) == {}
    # Address-only response
    out = map_building_data({"ehitis": {"ehitiseAndmed": {"taisaadress": "X"}}})
    assert out == {"address": "X"}


def test_map_building_data_coerces_strings_to_numbers() -> None:
    """EHR returns numbers as strings ("103.0", "2", etc) — make sure we coerce."""
    out = map_building_data(
        {
            "ehitis": {
                "ehitisePohiandmed": {
                    "ehitisalunePind": "103.0",
                    "korgus": "7,0",  # comma decimal
                    "maxKorrusteArv": "2",
                    "kavKasutusKp": "2018-06-01T00:00:00.000",
                }
            }
        }
    )
    assert out["footprint_m2"] == 103.0
    assert out["height_m"] == 7.0
    assert out["storeys_above"] == 2
    assert out["construction_year"] == 2018


def test_map_building_data_year_falls_back_to_eh_alust() -> None:
    """If kavKasutusKp is missing, use ehAlustKp (construction-start)."""
    out = map_building_data(
        {
            "ehitis": {
                "ehitisePohiandmed": {
                    "ehAlustKp": "1988-07-01T00:00:00.000",
                }
            }
        }
    )
    assert out["construction_year"] == 1988


def test_map_building_data_skips_bad_year() -> None:
    """Invalid year (out of [1700, 2100]) → no construction_year."""
    out = map_building_data(
        {"ehitis": {"ehitisePohiandmed": {"kavKasutusKp": "0001-01-01T00:00:00"}}}
    )
    assert "construction_year" not in out


def test_map_building_data_invalid_input() -> None:
    assert map_building_data(None) == {}  # type: ignore[arg-type]
    assert map_building_data("string") == {}  # type: ignore[arg-type]
    assert map_building_data({"ehitis": "not a dict"}) == {}


# ---------------------------------------------------------------------------
# Lookup / search HTTP integration — mocked
# ---------------------------------------------------------------------------


class _MockResponse:
    def __init__(self, json_data: list | dict, status: int = 200):
        self._data = json_data
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom", request=None, response=None  # type: ignore[arg-type]
            )

    def json(self) -> list | dict:
        return self._data


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch) -> None:
    """Redirect cache root so tests don't pollute the real cache dir."""
    monkeypatch.setattr("tadf.external.cache.CACHE_DIR", tmp_path)


def test_lookup_ehr_happy_path() -> None:
    fixture = _load("buildingData_102032773.json")

    def fake_get(self, url, **kwargs):
        assert "buildingData" in url
        assert kwargs.get("params") == {"ehr_code": "102032773"}
        return _MockResponse(fixture)

    with patch("httpx.Client.get", new=fake_get):
        out = lookup_ehr("102032773")

    assert out is not None
    assert out["ehr_code"] == "102032773"
    assert out["footprint_m2"] == 103.0


def test_lookup_ehr_404() -> None:
    """Server-side error returns None (caller falls back to manual entry)."""

    def fake_get(self, url, **kwargs):
        return _MockResponse({}, status=404)

    with patch("httpx.Client.get", new=fake_get):
        out = lookup_ehr("nonexistent")
    assert out is None


def test_lookup_ehr_empty_input() -> None:
    assert lookup_ehr("") is None
    assert lookup_ehr("   ") is None


def test_lookup_ehr_caches() -> None:
    """Second call doesn't hit the network."""
    fixture = _load("buildingData_102032773.json")
    call_count = 0

    def fake_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return _MockResponse(fixture)

    with patch("httpx.Client.get", new=fake_get):
        out1 = lookup_ehr("102032773")
        out2 = lookup_ehr("102032773")

    assert out1 == out2
    assert call_count == 1, "second call should hit cache"


def test_search_ehr_returns_hits() -> None:
    fixture = _load("getgeoobjectsbyaddress_102032773.json")

    def fake_get(self, url, **kwargs):
        assert "getgeoobjectsbyaddress" in url
        return _MockResponse(fixture)

    with patch("httpx.Client.get", new=fake_get):
        hits = search_ehr("102032773")

    assert len(hits) >= 1
    bldg = next((h for h in hits if h.object_type == "EHR_KOOD"), None)
    assert bldg is not None
    assert bldg.ehr_code == "102032773"
    assert "Linna AÜ 1062" in (bldg.address or "")
    assert bldg.use_purpose == "Suvila"


def test_search_ehr_includes_kataster_feature() -> None:
    """The geoinfo response includes both EHR and KAYK (cadastre) features."""
    fixture = _load("getgeoobjectsbyaddress_102032773.json")

    def fake_get(self, url, **kwargs):
        return _MockResponse(fixture)

    with patch("httpx.Client.get", new=fake_get):
        hits = search_ehr("102032773")

    kayk = next((h for h in hits if h.object_type == "KAYK"), None)
    assert kayk is not None
    assert kayk.kataster_no == "85101:004:0020"


def test_search_ehr_empty_query_skips_request() -> None:
    """No query → no HTTP call, empty list."""
    with patch("httpx.Client.get") as mock_get:
        hits = search_ehr("")
        hits2 = search_ehr("   ")
    assert hits == []
    assert hits2 == []
    mock_get.assert_not_called()


def test_search_ehr_handles_unexpected_shape() -> None:
    """If the API ever changes shape, return [] instead of crashing."""

    def fake_get(self, url, **kwargs):
        return _MockResponse({"unexpected": "shape"})

    with patch("httpx.Client.get", new=fake_get):
        hits = search_ehr("anything")
    assert hits == []
