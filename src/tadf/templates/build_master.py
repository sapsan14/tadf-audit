"""Build the docxtpl master templates programmatically — one per audit subtype.

The Phase 1 masters are generated from code so we can version-control them as a
script rather than as opaque binaries. Once the template stabilises and Fjodor
wants visual tweaks (fonts, headers, signatures with images) we switch to
hand-edited .docx per subtype — but for the MVP this keeps the loop fast.

Run via:
    uv run python -m tadf.templates.build_master
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

TEMPLATES_DIR = Path(__file__).parent
SUBTYPES = ("kasutuseelne", "korraline", "erakorraline")


def _h(doc: Document, text: str, level: int = 1) -> None:
    p = doc.add_heading(text, level=level)
    for r in p.runs:
        r.font.size = Pt(14 if level == 1 else 12)


def _p(doc: Document, text: str, *, bold: bool = False, center: bool = False) -> None:
    p = doc.add_paragraph()
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(11)


def build(subtype: str = "kasutuseelne") -> Path:
    doc = Document()

    # ---------- 0. TITTELLEHT ----------
    _p(doc, "{{ cover.title }}", bold=True, center=True)
    _p(doc, "Aadress: {{ building.address }}", center=True)
    _p(doc, "Ehitisregistri kood: {{ building.ehr_code }}", center=True)
    _p(doc, "Töö nr: {{ audit.display_no }}", center=True)
    doc.add_paragraph()
    _p(
        doc,
        "Auditi koostas: {{ composer.full_name }}, "
        "{% if composer.company %}{{ composer.company }}"
        "{% if composer.company_reg_nr %}, reg. nr {{ composer.company_reg_nr }}{% endif %}"
        "{% endif %}",
    )
    _p(
        doc,
        "Auditi kontrollis (vastutav pädev isik): {{ reviewer.full_name }}, "
        "kutsetunnistus {{ reviewer.kutsetunnistus_no }}"
        "{% if reviewer.qualification %}, {{ reviewer.qualification }}{% endif %}",
    )
    _p(doc, "Tellija: {{ client.name if client else '' }}")
    doc.add_paragraph()
    _p(doc, "{{ visit_date_str }}", center=True)

    doc.add_page_break()

    # ---------- 1. ÜLDOSA ----------
    _h(doc, "1. ÜLDOSA")

    _h(doc, "1.1. Ehitise auditi eesmärk", level=2)
    _p(doc, "{{ audit.purpose }}")

    _h(doc, "1.2. Ehitise auditori andmed", level=2)
    _p(doc, "Auditi liik: {{ audit_type_text }}")
    _p(doc, "Auditi koostas: {{ composer.full_name }}")
    _p(
        doc,
        "Vastutav pädev isik: {{ reviewer.full_name }}, kutsetunnistus {{ reviewer.kutsetunnistus_no }}",
    )
    _p(doc, "{{ independence_declaration }}")

    _h(doc, "1.3. Auditi ulatus", level=2)
    _p(doc, "{{ audit.scope }}")

    # ---------- 2. AUDITI OBJEKT ----------
    _h(doc, "2. AUDITI OBJEKT JA SELLE KIRJELDUS")
    _p(doc, "Objekti aadress: {{ building.address }}")
    _p(doc, "Ehitisregistri kood: {{ building.ehr_code }}")
    _p(doc, "Kasutusotstarve: {{ building.use_purpose }}")
    _p(doc, "Ehitusaasta: {{ building.construction_year }}")

    # ---------- 3. KINNISTU ----------
    _h(doc, "3. KINNISTU ASUKOHT JA PLANEERING")
    _p(doc, "Katastritunnus: {{ building.kataster_no }}")
    _p(doc, "Kinnistu pindala: {{ building.site_area_m2 }} m²")

    # ---------- 4. HOONE ÜLEVAATUS ----------
    _h(doc, "4. HOONE ÜLEVAATUS")
    _p(doc, "Paikvaatlus toimus {{ visit_date_str }} visuaalkontrolli teel.")
    doc.add_paragraph("{% for f in findings_section_4 %}")
    _p(doc, "• {{ f.observation }}")
    doc.add_paragraph("{% endfor %}")

    # ---------- 5-6. ARHITEKTUUR + KONSTRUKTSIOON ----------
    _h(doc, "5. HOONE ARHITEKTUURI- JA EHITUSLIK OSA")
    doc.add_paragraph("{% for f in findings_section_5 %}")
    _p(doc, "• {{ f.observation }}")
    doc.add_paragraph("{% endfor %}")

    _h(doc, "6. HOONE KONSTRUKTIIVNE OSA")
    doc.add_paragraph("{% for f in findings_section_6 %}")
    _p(doc, "• {{ f.observation }}")
    doc.add_paragraph("{% endfor %}")

    # ---------- 7. TEHNOSÜSTEEMID ----------
    _h(doc, "7. HOONE TEHNOSÜSTEEMID")
    doc.add_paragraph("{% for f in findings_section_7 %}")
    _p(doc, "• {{ f.observation }}")
    doc.add_paragraph("{% endfor %}")

    # ---------- 8. TULEKAITSE (conditional) ----------
    doc.add_paragraph("{% if building.fire_class %}")
    _h(doc, "8. HOONE TULEKAITSE OSA")
    _p(doc, "Tulepüsivusklass: {{ building.fire_class }}")
    doc.add_paragraph("{% for f in findings_section_8 %}")
    _p(doc, "• {{ f.observation }}")
    doc.add_paragraph("{% endfor %}")
    doc.add_paragraph("{% endif %}")

    # ---------- 10. TEHNILISED NÄITAJAD ----------
    _h(doc, "10. HOONE TEHNILISED NÄITAJAD")
    _p(doc, "Ehitisealune pind: {{ building.footprint_m2 }} m²")
    _p(doc, "Maht: {{ building.volume_m3 }} m³")
    _p(doc, "Maapealsete korruste arv: {{ building.storeys_above }}")
    _p(doc, "Maa-aluste korruste arv: {{ building.storeys_below }}")

    # ---------- 11. KOKKUVÕTE (auditor-only) ----------
    _h(doc, "11. KOKKUVÕTE")
    doc.add_paragraph("{% for f in findings_section_11 %}")
    _p(doc, "{{ f.observation }}")
    doc.add_paragraph("{% endfor %}")

    # ---------- 12. ÕIGUSLIKUD ALUSED ----------
    _h(doc, "12. AUDITI ÕIGUSLIKUD ALUSED JA ULATUS")
    _p(doc, "Käesolev audit on koostatud tuginedes:")
    doc.add_paragraph("{% for r in legal_refs %}")
    _p(doc, "• {{ r.code }} — {{ r.title_et }}")
    doc.add_paragraph("{% endfor %}")

    # ---------- 13. METOODIKA ----------
    _h(doc, "13. AUDITI METOODIKA")
    _p(doc, "{{ methodology }}")

    # ---------- 14. LÕPPHINNANG (auditor-only) ----------
    _h(doc, "14. AUDITI LÕPPHINNANG")
    doc.add_paragraph("{% for f in findings_section_14 %}")
    _p(doc, "{{ f.observation }}")
    doc.add_paragraph("{% endfor %}")

    # ---------- 15. ALLKIRJAD ----------
    _h(doc, "15. ALLKIRJAD")
    _p(doc, "Auditi koostas:")
    _p(
        doc,
        "{{ composer.full_name }}"
        "{% if composer.company %} ({{ composer.company }}"
        "{% if composer.company_reg_nr %}, reg. nr {{ composer.company_reg_nr }}{% endif %})"
        "{% endif %}",
    )
    _p(doc, "allkiri: digitaalselt")
    doc.add_paragraph()
    _p(doc, "Auditi kontrollis (vastutav pädev isik):")
    _p(doc, "{{ reviewer.full_name }}, kutsetunnistus {{ reviewer.kutsetunnistus_no }}")
    _p(doc, "allkiri: digitaalselt")
    doc.add_paragraph()
    _p(doc, "{{ retention_notice }}")

    out = TEMPLATES_DIR / f"ea_{subtype}.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


def build_all() -> list[Path]:
    """Build one template per subtype. Bodies are identical today; the variation
    lives in `boilerplate.yaml` (audit_purpose) and `context_builder` (label)."""
    return [build(s) for s in SUBTYPES]


if __name__ == "__main__":
    for p in build_all():
        print(f"wrote {p}")
