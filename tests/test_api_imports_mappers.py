"""Field-mapping for raw EHR / Teatmik payloads."""

from __future__ import annotations

from tadf.api.imports import map_ehr, map_teatmik


def test_ehr_basic_fields() -> None:
    payload = {
        "address": "Auga 8, Narva-Jõesuu",
        "ehrCode": "102032773",
        "constructionYear": 2018,
        "footprint": 75.5,
    }
    out = map_ehr(payload)
    assert out["address"] == "Auga 8, Narva-Jõesuu"
    assert out["ehr_code"] == "102032773"
    assert out["construction_year"] == 2018
    assert out["footprint_m2"] == 75.5


def test_ehr_estonian_field_names() -> None:
    """The mapping table accepts both English and Estonian (camelCase) names."""
    payload = {
        "ehitisealunePind": "120,5",
        "korgus": "8.2",
        "korruseteArvMaapeal": "2",
    }
    out = map_ehr(payload)
    assert out["footprint_m2"] == 120.5  # comma decimal coerced
    assert out["height_m"] == 8.2
    assert out["storeys_above"] == 2


def test_ehr_fire_class_normalised() -> None:
    assert map_ehr({"fireClass": "TP-1"})["fire_class"] == "TP-1"
    assert map_ehr({"fireClass": "tp1"})["fire_class"] == "TP-1"
    assert map_ehr({"fireClass": "TP 2"})["fire_class"] == "TP-2"
    assert map_ehr({"fireClass": "garbage"}).get("fire_class") is None


def test_ehr_nested_payload() -> None:
    """EHR sometimes wraps the building object — try common shapes."""
    payload = {"building": {"address": "X", "ehrCode": "9"}}
    out = map_ehr(payload)
    assert out["address"] == "X"
    assert out["ehr_code"] == "9"


def test_ehr_unknown_keys_ignored() -> None:
    out = map_ehr({"randomField": "x", "address": "Y"})
    assert out == {"address": "Y"}


def test_teatmik_basic() -> None:
    payload = {
        "name": "UNTWERP OÜ",
        "reg_code": "14332941",
        "address": "Tallinn, Pärnu mnt 5",
        "status": "active",
    }
    assert map_teatmik(payload) == payload


def test_teatmik_drops_empty() -> None:
    out = map_teatmik({"name": "X", "reg_code": "", "address": None})
    assert out == {"name": "X"}
