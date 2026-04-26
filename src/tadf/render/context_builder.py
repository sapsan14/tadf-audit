"""Build a docxtpl render context from an Audit aggregate.

The context is the single source of truth for the rendered DOCX — `context.json`
is also persisted under `data/audits/<id>/` for reproducibility / 7-year
retention.
"""

from __future__ import annotations

from typing import Any

import yaml

from tadf.legal.loader import for_section
from tadf.models import Audit
from tadf.templates import BOILERPLATE_PATH

AUDIT_TYPE_LABELS = {
    ("EA", "kasutuseelne"): "Ehitise kasutuseelne audit (EhS § 18 alusel)",
    ("EA", "korraline"): "Ehitise korraline audit (EhS § 18 alusel)",
    ("EA", "erakorraline"): "Ehitise erakorraline audit (EhS § 18 alusel)",
    ("EP", "kasutuseelne"): "Ehitusprojekti kasutuseelne audit",
    ("EP", "korraline"): "Ehitusprojekti audit",
    ("TJ", "kasutuseelne"): "Tehniline järelevalve",
    ("TP", "kasutuseelne"): "Tehniline projekt — audit",
    ("AU", "korraline"): "Institutsionaalse ehitise audit",
}


def _findings_for(audit: Audit, section_prefix: str) -> list[dict[str, Any]]:
    """Findings whose section_ref starts with the given prefix.

    A finding stamped section_ref='6.1' falls under both '6' and '6.1'. Use
    `accepted_polished` flag to decide which text variant to render.
    """
    out = []
    for f in audit.findings:
        if not f.section_ref.startswith(section_prefix):
            continue
        text = f.observation_polished if f.accepted_polished and f.observation_polished else f.observation_raw
        out.append({"observation": text, "severity": f.severity, "section_ref": f.section_ref})
    return out


def _audit_type_text(audit: Audit) -> str:
    return AUDIT_TYPE_LABELS.get(
        (audit.type, audit.subtype),
        f"{audit.type} — {audit.subtype}",
    )


def build_context(audit: Audit) -> dict[str, Any]:
    """Return the dict consumed by docxtpl.render(context)."""
    bp = yaml.safe_load(BOILERPLATE_PATH.read_text(encoding="utf-8"))
    methodology = bp["methodology"][audit.methodology_version]
    purpose_default = bp["audit_purpose"].get(audit.subtype, "")

    purpose = audit.purpose or purpose_default

    # Cover convenience block
    cover_title = f"{audit.building.use_purpose or 'EHITISE'} AUDITI ARUANNE".upper()

    legal_refs = [{"code": r.code, "title_et": r.title_et} for r in for_section("12", audit.type)]

    ctx: dict[str, Any] = {
        "audit": {
            "display_no": audit.display_no(),
            "type": audit.type,
            "subtype": audit.subtype,
            "purpose": purpose,
            "scope": audit.scope or "",
            "methodology_version": audit.methodology_version,
        },
        "audit_type_text": _audit_type_text(audit),
        "visit_date_str": audit.visit_date.strftime("%d.%m.%Y"),
        "cover": {"title": cover_title},
        "composer": audit.composer.model_dump(),
        "reviewer": audit.reviewer.model_dump(),
        "building": audit.building.model_dump(),
        "client": audit.client.model_dump() if audit.client else None,
        "independence_declaration": bp["independence_declaration"].strip(),
        "methodology": methodology.strip(),
        "retention_notice": bp["retention_notice"].strip(),
        "legal_refs": legal_refs,
    }

    # Per-section finding lists used by the template's {% for %} loops
    for n in ("4", "5", "6", "7", "8", "11", "14"):
        ctx[f"findings_section_{n}"] = _findings_for(audit, n)

    return ctx
