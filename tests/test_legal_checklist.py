from __future__ import annotations

from tadf.legal.checklist import check, passes, soft_warnings
from tadf.models import Finding


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


def test_soft_warning_fires_for_major_finding_without_legal_ref(audit):
    audit.findings.append(
        Finding(
            section_ref="6.1",
            severity="nonconf_major",
            observation_raw="Vundamendi pragunemine.",
            legal_ref_codes=[],
        )
    )
    warnings = soft_warnings(audit)
    assert any(
        w.field.endswith(".legal_ref_codes") for w in warnings
    ), [w.field for w in warnings]


def test_soft_warning_skips_info_severity(audit):
    audit.findings.append(
        Finding(
            section_ref="6.1",
            severity="info",
            observation_raw="Hoone üldine seisukord rahuldav.",
            legal_ref_codes=[],
        )
    )
    warnings = soft_warnings(audit)
    assert not any(w.field.endswith("[2].legal_ref_codes") for w in warnings)


def test_soft_warning_skips_locked_sections(audit):
    audit.findings.append(
        Finding(
            section_ref="11",
            severity="nonconf_major",
            observation_raw="Kokkuvõte test.",
            legal_ref_codes=[],
        )
    )
    warnings = soft_warnings(audit)
    # The new finding is at index len-1; its field shouldn't appear because
    # section 11 is auditor-only and excluded from the soft check.
    last_idx = len(audit.findings) - 1
    assert not any(f"[{last_idx}].legal_ref_codes" in w.field for w in warnings)
