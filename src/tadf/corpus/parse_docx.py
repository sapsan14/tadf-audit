"""Parse a TADF .docx audit report into a structured dict.

Heuristics, not a full grammar — the corpus uses no Word heading styles, so
section boundaries are detected from text patterns observed across the 12
historical reports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docx import Document

# Top-level section heading: "1. ÜLDOSA", "2. AUDITI OBJEKT JA SELLE KIRJELDUS",
# also accepts a leading group label like "ARHITEKTUURI- JA EHITUSLIK OSA"
# (which is then immediately followed by a numbered section line).
SECTION_RE = re.compile(r"^\s*(\d{1,2})\.\s+([A-ZÄÖÜÕŠŽ][^\n]{2,})$")
SUBSECTION_RE = re.compile(r"^\s*(\d{1,2}\.\d{1,2})\.?\s+(.+)$")
TOC_LINE_RE = re.compile(r"\.{3,}\s*lk\s+\d", re.IGNORECASE)


@dataclass
class CoverInfo:
    title: str | None = None
    address: str | None = None
    ehr_code: str | None = None
    composer_name: str | None = None
    composer_company: str | None = None
    composer_reg_nr: str | None = None
    reviewer_name: str | None = None
    reviewer_kutsetunnistus: str | None = None
    reviewer_qualification: str | None = None
    client: str | None = None
    audit_type: str | None = None  # e.g. "Ehitise kasutuseelne audit (EhS §18 alusel)"
    location_date: str | None = None


@dataclass
class Section:
    number: str
    title: str
    body: list[str] = field(default_factory=list)


@dataclass
class ParsedReport:
    source_path: str
    cover: CoverInfo
    sections: list[Section]
    raw_paragraphs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "cover": self.cover.__dict__,
            "sections": [{"number": s.number, "title": s.title, "body": s.body} for s in self.sections],
        }


def _extract_cover(paragraphs: list[str]) -> CoverInfo:
    """Cover page is roughly the first ~18 non-empty paragraphs before 'Sisukord'."""
    cover = CoverInfo()
    head: list[str] = []
    for p in paragraphs:
        if p.strip().lower().startswith("sisukord"):
            break
        head.append(p)

    # Title = first non-empty line
    for line in head:
        if line.strip():
            cover.title = line.strip()
            break

    joined = "\n".join(head)

    if m := re.search(r"Aadress:\s*([^\n]+?)(?:\s+Ehitisregistri\s+kood|$)", joined, re.IGNORECASE):
        cover.address = m.group(1).strip()
    if m := re.search(r"Ehitisregistri\s+kood:?\s*(\d{6,12})", joined, re.IGNORECASE):
        cover.ehr_code = m.group(1)

    if m := re.search(r"Auditi\s+koostas:\s*([^\n]+)", joined, re.IGNORECASE):
        line = m.group(1).strip()
        parts = [p.strip() for p in line.split(",")]
        cover.composer_name = parts[0] if parts else None
        if len(parts) >= 2:
            cover.composer_company = parts[1]
        if r := re.search(r"reg\.?\s*nr\.?\s*(\d{6,10})", line, re.IGNORECASE):
            cover.composer_reg_nr = r.group(1)

    if m := re.search(r"Auditi\s+kontrollis[^:]*:\s*([^\n]+)", joined, re.IGNORECASE):
        line = m.group(1).strip()
        if r := re.search(r"^([^,]+?)(?:,|\s+kutsetunnistus|$)", line, re.IGNORECASE):
            cover.reviewer_name = r.group(1).strip()
        if r := re.search(r"kutsetunnistus\s*(\d{4,8})", line, re.IGNORECASE):
            cover.reviewer_kutsetunnistus = r.group(1)
        if r := re.search(r"(Diplomeerit[^,\n]*)", line, re.IGNORECASE):
            cover.reviewer_qualification = r.group(1).strip()

    if m := re.search(r"Tellija:\s*([^\n]+)", joined, re.IGNORECASE):
        cover.client = m.group(1).strip()

    if m := re.search(r"Auditi\s+liik:\s*([^\n]+)", joined, re.IGNORECASE):
        cover.audit_type = m.group(1).strip()

    # Location + date line such as "Sillamäe, Ida-Virumaa, 03.07.2025"
    for line in head:
        if re.search(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", line):
            cover.location_date = line.strip()
            break

    return cover


def _is_toc_line(text: str) -> bool:
    return bool(TOC_LINE_RE.search(text))


def _split_sections(paragraphs: list[str]) -> list[Section]:
    """Find numbered section headings after the TOC and group following paragraphs."""
    sections: list[Section] = []
    current: Section | None = None
    past_toc = False

    for raw in paragraphs:
        text = raw.strip()
        if not text:
            continue

        # Skip the table of contents block — its lines look like headings.
        if _is_toc_line(text):
            past_toc = True
            continue

        m = SECTION_RE.match(text)
        if m and past_toc:
            if current is not None:
                sections.append(current)
            current = Section(number=m.group(1), title=m.group(2).strip())
            continue

        if current is not None:
            current.body.append(text)

    if current is not None:
        sections.append(current)
    return sections


def parse_docx(path: str | Path) -> ParsedReport:
    path = Path(path)
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs]
    cover = _extract_cover(paragraphs)
    sections = _split_sections(paragraphs)
    return ParsedReport(
        source_path=str(path),
        cover=cover,
        sections=sections,
        raw_paragraphs=paragraphs,
    )
