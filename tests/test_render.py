from __future__ import annotations

import json

import pytest
from docx import Document

from tadf.render.docx_render import ChecklistFailed, render_to_path


def test_render_writes_docx_and_context(audit, tmp_path):
    out = render_to_path(audit, tmp_path)
    assert out.exists()
    assert out.stat().st_size > 5_000  # not an empty stub
    assert (tmp_path / "context.json").exists()
    ctx = json.loads((tmp_path / "context.json").read_text(encoding="utf-8"))
    assert ctx["composer"]["full_name"] == "Aleksei Sholokhov"
    assert ctx["reviewer"]["kutsetunnistus_no"] == "148515"


def test_render_contains_key_estonian_strings(audit, tmp_path):
    out = render_to_path(audit, tmp_path)
    body = "\n".join(p.text for p in Document(str(out)).paragraphs)

    # Section headings
    assert "ÜLDOSA" in body
    assert "AUDITI OBJEKT JA SELLE KIRJELDUS" in body
    assert "TULEKAITSE" in body  # conditional on fire_class
    assert "KOKKUVÕTE" in body
    assert "LÕPPHINNANG" in body

    # Filled values
    assert "148515" in body
    assert "Fjodor Sokolov" in body
    assert "Aleksei Sholokhov" in body
    assert "Linna AÜ 1062" in body
    assert "TP-3" in body

    # Boilerplate
    assert "kutsetunnistus" in body.lower()
    assert "sõltumatud" in body  # independence_declaration
    assert "metoodili" in body.lower()  # methodology block


def test_render_blocks_when_checklist_fails(audit, tmp_path):
    audit.purpose = None
    with pytest.raises(ChecklistFailed):
        render_to_path(audit, tmp_path, enforce_checklist=True)


def test_render_force_when_checklist_disabled(audit, tmp_path):
    audit.purpose = None
    out = render_to_path(audit, tmp_path, enforce_checklist=False)
    assert out.exists()


def test_no_fire_class_skips_section_8(audit, tmp_path):
    audit.building.fire_class = None
    audit.findings = [f for f in audit.findings if not f.section_ref.startswith("8")]
    out = render_to_path(audit, tmp_path)
    body = "\n".join(p.text for p in Document(str(out)).paragraphs)
    assert "TULEKAITSE" not in body
