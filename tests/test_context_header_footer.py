"""Header/footer context-builder logic for the rendered DOCX."""

from __future__ import annotations

from tadf.render.context_builder import (
    build_context,
    default_footer_text,
    default_header_text,
)


def test_default_header_includes_work_no_and_address(audit) -> None:
    h = default_header_text(audit)
    assert f"{audit.seq_no}/{audit.year}" in h
    assert "Töö nimetus" in h
    assert audit.building.address.split(",")[0] in h  # address slug


def test_default_footer_lists_reviewer_and_kutsetunnistus(audit) -> None:
    f = default_footer_text(audit)
    assert audit.reviewer.full_name in f
    assert audit.reviewer.kutsetunnistus_no in f
    assert "Pädev isik" in f


def test_context_uses_override_when_set(audit) -> None:
    audit.header_override = "🔧 Custom override header"
    audit.footer_override = "🔧 Custom override footer"
    ctx = build_context(audit)
    assert ctx["page_header"] == "🔧 Custom override header"
    assert ctx["page_footer"] == "🔧 Custom override footer"


def test_context_falls_back_to_default_when_none(audit) -> None:
    audit.header_override = None
    audit.footer_override = None
    ctx = build_context(audit)
    assert "Töö nimetus" in ctx["page_header"]
    assert "Pädev isik" in ctx["page_footer"]


def test_context_falls_back_when_empty_string(audit) -> None:
    """Empty string is treated like None (auditor cleared the field)."""
    audit.header_override = ""
    audit.footer_override = ""
    ctx = build_context(audit)
    assert "Töö nimetus" in ctx["page_header"]
    assert "Pädev isik" in ctx["page_footer"]
