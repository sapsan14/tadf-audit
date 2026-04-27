"""Deep-link builders for EHR.ee and Teatmik.ee."""

from __future__ import annotations

from tadf.external.links import ehr_building_url, teatmik_company_url


def test_ehr_link_by_code() -> None:
    url = ehr_building_url(ehr_code="102032773")
    assert url is not None
    assert "102032773" in url
    assert url.startswith("https://livekluster.ehr.ee/")


def test_ehr_link_strips_whitespace() -> None:
    url = ehr_building_url(ehr_code="  102032773  ")
    assert url is not None
    assert "  " not in url
    assert "102032773" in url


def test_ehr_link_by_kataster_when_no_code() -> None:
    url = ehr_building_url(ehr_code=None, kataster="85101:004:0020")
    assert url is not None
    # `:` is URL-encoded as %3A by quote()
    assert "85101%3A004%3A0020" in url


def test_ehr_link_none_when_both_empty() -> None:
    assert ehr_building_url() is None
    assert ehr_building_url(ehr_code="", kataster="") is None
    assert ehr_building_url(ehr_code="   ", kataster=None) is None


def test_teatmik_reg_code_goes_to_personlegal() -> None:
    url = teatmik_company_url("14332941")
    assert url is not None
    assert "personlegal/14332941" in url


def test_teatmik_name_goes_to_search() -> None:
    url = teatmik_company_url("UNTWERP OÜ")
    assert url is not None
    assert "search?query=" in url
    assert "UNTWERP" in url


def test_teatmik_url_encodes_special_chars() -> None:
    url = teatmik_company_url("AS Teede & Sillad")
    assert url is not None
    assert "%26" in url or "&" not in url.split("query=", 1)[1]


def test_teatmik_empty_returns_none() -> None:
    assert teatmik_company_url("") is None
    assert teatmik_company_url("   ") is None
