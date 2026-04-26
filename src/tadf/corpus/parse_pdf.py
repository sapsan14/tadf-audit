"""Parse a TADF audit report PDF into the same structured shape as parse_docx.

The corpus has two distinct authoring styles:
  - "TADF style" (Fjodor's newer reports): 4-level numbering (1.5.1, 2.2.3.1)
  - "UNTWERP style": 2-level numbering, all-caps top-level headings

We use a permissive heading regex that catches both, plus a cover regex that
recognises both label dialects ('Auditi koostas' vs 'Pädev isik').
"""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber

from tadf.corpus.parse_docx import CoverInfo, ParsedReport, Section

# Heading examples from corpus:
#   "1. ÜLDOSA"
#   "1.5.1 TADF Ehitus OÜ"
#   "2.2.3.1 Ehitise koordinaadid"
#   "8.1. Üldiseloomustus ja normid"
HEADING_RE = re.compile(
    r"^\s*(\d{1,2}(?:\.\d{1,3}){0,4})\.?\s+([A-ZÄÖÜÕa-zäöüõ][^\n]{2,150})$",
    re.MULTILINE,
)


def _extract_text(path: Path) -> str:
    pages: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _extract_cover(text: str) -> CoverInfo:
    """Heuristic cover-page extraction. Works on both report styles."""
    cover = CoverInfo()

    # Title — first non-trivial line that looks like a title
    for line in text.splitlines()[:10]:
        s = line.strip()
        if s and len(s) > 5 and not s.lower().startswith("töö nr"):
            cover.title = s
            break

    if m := re.search(r"Aadress:\s*([^\n]+)", text, re.IGNORECASE):
        cover.address = m.group(1).strip()
    m_ehr = re.search(r"EHR\s*reg\.?kood:?\s*(\d{6,12})", text, re.IGNORECASE) or re.search(
        r"Ehitisregistri\s+kood:?\s*(\d{6,12})", text, re.IGNORECASE
    )
    if m_ehr:
        cover.ehr_code = m_ehr.group(1)

    if m := re.search(r"Katastritunnus:?\s*([\d:]+)", text):
        # store on title field is already taken; we don't have a kataster slot in CoverInfo
        # but the parsed_report consumer knows to look in raw_paragraphs
        pass

    if m := re.search(r"Tellija:?\s*([^\n]+)", text, re.IGNORECASE):
        cover.client = m.group(1).strip()

    m_rev = re.search(r"Pädev\s+isik:?\s*([^\n,]+?)(?:,|$)", text, re.IGNORECASE) or re.search(
        r"Auditi\s+kontrollis[^:]*:\s*([^\n,]+)", text, re.IGNORECASE
    )
    if m_rev:
        cover.reviewer_name = m_rev.group(1).strip()

    if m := re.search(r"kutsetunnistus\s*(\d{4,8})", text, re.IGNORECASE):
        cover.reviewer_kutsetunnistus = m.group(1)
    if m := re.search(r"(Diplomeeritud[^\n,]*)", text, re.IGNORECASE):
        cover.reviewer_qualification = m.group(1).strip()

    if m := re.search(r"Auditi\s+koostas:?\s*([^\n,]+)", text, re.IGNORECASE):
        cover.composer_name = m.group(1).strip()
    elif m := re.search(
        r"Ehitise\s+auditi\s+tegija:?\s*([^,\n]+?)(?:,\s*registrikood\s+(\d+))?", text, re.IGNORECASE
    ):
        cover.composer_company = m.group(1).strip()
        if m.group(2):
            cover.composer_reg_nr = m.group(2)

    # In TADF-style reports, the 'pädev isik' is also the composer
    if not cover.composer_name and cover.reviewer_name:
        cover.composer_name = cover.reviewer_name

    if m := re.search(r"Auditi\s+liik:?\s*([^\n]+)", text, re.IGNORECASE):
        cover.audit_type = m.group(1).strip()
    elif "erakorraline" in text.lower()[:2000]:
        cover.audit_type = "erakorraline audit"
    elif "kasutuseelne" in text.lower()[:2000]:
        cover.audit_type = "kasutuseelne audit"
    elif "korraline" in text.lower()[:2000]:
        cover.audit_type = "korraline audit"

    if m := re.search(r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b", text):
        cover.location_date = m.group(1)

    return cover


def _split_sections(text: str) -> list[Section]:
    """Split the body into sections using the universal heading regex."""
    matches = list(HEADING_RE.finditer(text))
    sections: list[Section] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body_text = text[m.end() : end].strip()
        # Limit body to first ~3000 chars per section (some sections are long
        # and would otherwise dominate the corpus JSON).
        body_paragraphs = [p.strip() for p in body_text.split("\n") if p.strip()][:60]
        sections.append(Section(number=m.group(1), title=m.group(2).strip(), body=body_paragraphs))
    return sections


def parse_pdf(path: str | Path) -> ParsedReport:
    path = Path(path)
    text = _extract_text(path)
    cover = _extract_cover(text)
    sections = _split_sections(text)
    return ParsedReport(
        source_path=str(path),
        cover=cover,
        sections=sections,
        raw_paragraphs=text.splitlines(),
    )
