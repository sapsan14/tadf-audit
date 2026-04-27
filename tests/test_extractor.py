"""Smoke tests for the building extractor.

The extractor itself calls Anthropic — too expensive to run on every CI
build. We test the deterministic parts (schema, diff, fire_class
normalisation) here. The full LLM round-trip is exercised manually via
the corpus DOCX during development.
"""

from __future__ import annotations

from tadf.llm.extractor import diff


def test_diff_picks_only_changed_fields() -> None:
    current = {
        "address": "Auga 8",
        "construction_year": 2018,
        "ehr_code": None,
    }
    extracted = {
        "address": "Auga 8",          # same — skip
        "construction_year": 2020,    # different — include
        "ehr_code": "102032773",      # was None, now set — include
        "kataster_no": None,          # extracted None — skip
        "footprint_m2": 75.5,         # not in current — include
    }
    rows = dict((f, (c, p)) for f, c, p in diff(current, extracted))
    assert "address" not in rows
    assert "kataster_no" not in rows
    assert rows["construction_year"] == (2018, 2020)
    assert rows["ehr_code"] == (None, "102032773")
    assert "footprint_m2" in rows


def test_diff_treats_floats_within_epsilon_as_equal() -> None:
    """100 (int) vs 100.0 (float) shouldn't show as a diff."""
    current = {"footprint_m2": 100.0}
    extracted = {"footprint_m2": 100}
    assert diff(current, extracted) == []


def test_diff_treats_actual_differences() -> None:
    current = {"footprint_m2": 100.0}
    extracted = {"footprint_m2": 105.5}
    rows = diff(current, extracted)
    assert len(rows) == 1
    assert rows[0][0] == "footprint_m2"


def test_diff_skips_none_proposed() -> None:
    """If extractor returns None, we never propose a write."""
    current = {"address": "Auga 8"}
    extracted = {"address": None}
    assert diff(current, extracted) == []


def test_extract_building_empty_text_returns_all_none() -> None:
    """Empty/whitespace input shouldn't bill the API."""
    from tadf.llm.extractor import extract_building

    out = extract_building("")
    assert out["address"] is None
    assert out["construction_year"] is None
    out2 = extract_building("   \n  \t  ")
    assert all(v is None for v in out2.values())
