"""Deep-link builders for EHR.ee and Teatmik.ee."""

from __future__ import annotations

from tadf.external.links import (
    ehr_building_url,
    maaamet_kataster_url,
    teatmik_company_url,
)


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
    # Teatmik uses path-style search, not ?query=…
    assert "/et/search/" in url
    assert "UNTWERP" in url


def test_teatmik_url_encodes_special_chars() -> None:
    url = teatmik_company_url("AS Teede & Sillad")
    assert url is not None
    # `&` must be percent-encoded so it's part of the path, not a separator.
    assert "%26" in url


def test_teatmik_empty_returns_none() -> None:
    assert teatmik_company_url("") is None
    assert teatmik_company_url("   ") is None


def test_maaamet_url_uses_ky_kataster_ee() -> None:
    url = maaamet_kataster_url("85101:004:0020")
    assert url is not None
    # «Kiirpäring katastrist» — the quick-lookup SPA on a dedicated
    # subdomain that consumes katastritunnus from the path segment.
    # Format documented verbatim by Maa-amet on the geoportaal page.
    # The earlier `kataster.ee/?nr=…` was the homepage and ignored the
    # query string; xgis2 variants only loaded the SPA shell.
    assert url == "https://ky.kataster.ee/ky/85101:004:0020"


def test_maaamet_url_none_for_empty_input() -> None:
    assert maaamet_kataster_url(None) is None
    assert maaamet_kataster_url("") is None
    assert maaamet_kataster_url("   ") is None


def test_maaamet_xgis_backup_url_still_uses_xgis2() -> None:
    """The xgis2 link is kept as a backup in case kataster.ee is down —
    it just needs to round-trip the kataster value, even if the SPA may
    not always honour it."""
    from tadf.external.links import maaamet_xgis_kataster_url

    url = maaamet_xgis_kataster_url("85101:004:0020")
    assert url is not None
    assert url.startswith("https://xgis.maaamet.ee/xgis2/page/app/maainfo")
    assert "85101%3A004%3A0020" in url
    assert maaamet_xgis_kataster_url("") is None
    assert maaamet_xgis_kataster_url(None) is None
