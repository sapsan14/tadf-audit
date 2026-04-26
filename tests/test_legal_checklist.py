from __future__ import annotations

from tadf.legal.checklist import check, passes


def test_minimal_audit_passes(audit):
    assert passes(audit), [str(m) for m in check(audit)]


def test_missing_purpose_fails(audit):
    audit.purpose = None
    fields = {m.field for m in check(audit)}
    assert "audit.purpose" in fields


def test_missing_kutsetunnistus_fails(audit):
    audit.reviewer.kutsetunnistus_no = None
    fields = {m.field for m in check(audit)}
    assert "reviewer.kutsetunnistus_no" in fields


def test_missing_section_11_fails(audit):
    audit.findings = [f for f in audit.findings if not f.section_ref.startswith("11")]
    fields = {m.field for m in check(audit)}
    assert "findings[section=11]" in fields


def test_missing_section_14_fails(audit):
    audit.findings = [f for f in audit.findings if not f.section_ref.startswith("14")]
    fields = {m.field for m in check(audit)}
    assert "findings[section=14]" in fields


def test_fire_class_requires_section_8(audit):
    # Remove fire-safety findings; fire_class is set => should fail
    audit.findings = [f for f in audit.findings if not f.section_ref.startswith("8")]
    fields = {m.field for m in check(audit)}
    assert "findings[section=8]" in fields


def test_no_fire_class_no_section_8_required(audit):
    audit.building.fire_class = None
    audit.findings = [f for f in audit.findings if not f.section_ref.startswith("8")]
    # Should still pass — no fire_class means no section-8 requirement
    assert passes(audit)


def test_pre_2003_substitute_docs_satisfies_construction_year(audit):
    audit.building.construction_year = None
    audit.building.pre_2003 = True
    audit.building.substitute_docs_note = "Originaaldokumendid puuduvad; audit asendab."
    fields = {m.field for m in check(audit)}
    assert "building.construction_year" not in fields
