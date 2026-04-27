"""Ingest historical audit reports into the `corpus_audit` + `corpus_section`
tables.

Separate from `preload.py` (which imports one report as an `audit` draft for
viewing in the UI). This module is the **training corpus** — provider-agnostic
records that any LLM (Claude, GPT, Gemini, local Llama) can consume as
few-shot examples.

Idempotency key is `source_sha256` — the SHA-256 of the original file's
bytes. Re-running ingest on the same file is a no-op; replacing a file with
edited content re-imports it as a fresh row.

Section normalisation: `parse_*.py` returns `raw_number` like "6", "6.1",
"8.7"; we map onto the canonical `tadf.sections.SECTION_KEYS` when the
number matches a known key, else leave `section_ref = None` (still indexed
on `raw_number` for traceability).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from tadf.corpus.parse_asice import parse_asice
from tadf.corpus.parse_doc import LibreofficeMissing, parse_doc
from tadf.corpus.parse_docx import ParsedReport, parse_docx
from tadf.corpus.parse_pdf import parse_pdf
from tadf.db.orm import CorpusAuditRow, CorpusSectionRow
from tadf.db.session import session_scope
from tadf.sections import SECTION_LABELS

PARSERS = {
    ".docx": parse_docx,
    ".pdf": parse_pdf,
    ".asice": parse_asice,
    ".doc": parse_doc,
}

# The corpus uses two distinct leading-prefix conventions:
#   1. SSYYYY  — 2-digit sequence + 4-digit year (newer TADF style),
#      e.g. "012026_EP_..." -> seq=1, year=2026
#   2. DDMMYY  — date in 6 digits (older style),
#      e.g. "100825_TJ_..." -> day=10, month=8, year=2025
# We try (1) first, fall back to (2). The trailing date in the filename
# (if present) always wins for the year.
LEADING_SS_YYYY_RE = re.compile(r"^(?P<seq>\d{1,3})(?P<year>\d{4})_(?P<type>[A-Z]{1,3})_")
LEADING_DDMMYY_RE = re.compile(r"^(?P<dd>\d{2})(?P<mm>\d{2})(?P<yy>\d{2})_(?P<type>[A-Z]{1,3})_")
TRAILING_DATE_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\D*$")
TRAILING_DATE_DMY_RE = re.compile(r"_(\d{2})(\d{2})(\d{4})\D*$")

SUBTYPE_KEYWORDS = {
    "kasutuseelne": ("kasutuseelne",),
    "erakorraline": ("erakorraline",),
    "korraline": ("korraline",),
}

# Include both pickable subsections and auto-populated top-level numbers
# (1 Üldosa, 2 Objekt, 3 Kinnistu, 12 Õiguslikud alused, 15 Allkirjad). All of
# them are valid canonical refs as far as the corpus is concerned.
_SECTION_KEY_SET = set(SECTION_LABELS.keys())


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _infer_meta(stem: str) -> tuple[int | None, int | None, str | None]:
    seq_no: int | None = None
    year: int | None = None
    audit_kind: str | None = None

    # Try newer SSYYYY convention first (e.g. "012026_EP_" -> seq=1, year=2026).
    if m := LEADING_SS_YYYY_RE.match(stem):
        candidate_year = int(m.group("year"))
        if 2000 <= candidate_year <= 2099:
            seq_no = int(m.group("seq"))
            year = candidate_year
            audit_kind = m.group("type")
    # Fall back to DDMMYY date convention (e.g. "100825_TJ_" -> day=10/8/25).
    if year is None and (m := LEADING_DDMMYY_RE.match(stem)):
        dd = int(m.group("dd"))
        mm = int(m.group("mm"))
        yy = int(m.group("yy"))
        if 1 <= dd <= 31 and 1 <= mm <= 12:
            year = 2000 + yy
            audit_kind = m.group("type")

    # Trailing date in the filename overrides whatever the prefix said.
    if m := TRAILING_DATE_ISO_RE.search(stem):
        year = int(m.group(1))
    elif m := TRAILING_DATE_DMY_RE.search(stem):
        year = int(m.group(3))
    return seq_no, year, audit_kind


def _infer_subtype(report: ParsedReport) -> str | None:
    haystack = (report.cover.audit_type or "").lower()
    haystack += " " + " ".join(s.title.lower() for s in report.sections[:5])
    for subtype, kws in SUBTYPE_KEYWORDS.items():
        if any(kw in haystack for kw in kws):
            return subtype
    return None


def _normalise_section_ref(raw_number: str) -> str | None:
    """Map a parser's raw section number to the canonical TADF key, if known."""
    if raw_number in _SECTION_KEY_SET:
        return raw_number
    # Top-level sections (e.g. "6") are listed too — already covered above.
    # Some PDFs over-number (e.g. "1.5.1.3"); strip trailing levels until match.
    parts = raw_number.split(".")
    while len(parts) > 1:
        parts.pop()
        candidate = ".".join(parts)
        if candidate in _SECTION_KEY_SET:
            return candidate
    return None


def _report_to_rows(
    path: Path,
    sha256: str,
    report: ParsedReport,
) -> tuple[CorpusAuditRow, list[CorpusSectionRow]]:
    seq_no, year, audit_kind = _infer_meta(path.stem)
    subtype = _infer_subtype(report)

    audit_row = CorpusAuditRow(
        source_path=str(path),
        source_sha256=sha256,
        source_format=path.suffix.lower().lstrip("."),
        filename=path.name,
        seq_no=seq_no,
        year=year,
        audit_kind=audit_kind,
        subtype=subtype,
        title=report.cover.title,
        address=report.cover.address,
        ehr_code=report.cover.ehr_code,
        composer_name=report.cover.composer_name,
        composer_company=report.cover.composer_company,
        reviewer_name=report.cover.reviewer_name,
        cover_json=json.dumps(asdict(report.cover), ensure_ascii=False),
    )

    sections: list[CorpusSectionRow] = []
    for s in report.sections:
        body = "\n".join(s.body).strip()
        if not body:
            continue
        sections.append(
            CorpusSectionRow(
                raw_number=s.number,
                section_ref=_normalise_section_ref(s.number),
                title=s.title,
                body_text=body,
            )
        )
    return audit_row, sections


def ingest_file(path: Path) -> tuple[str, int | None]:
    """Ingest a single audit file. Returns (status, audit_id) where status is
    one of: "imported", "skip-duplicate", "skip-format", "skip-no-libreoffice",
    "error:<msg>". audit_id is None unless status == "imported".
    """
    ext = path.suffix.lower()
    parser = PARSERS.get(ext)
    if parser is None:
        return ("skip-format", None)

    sha256 = _file_sha256(path)
    with session_scope() as s:
        existing = (
            s.query(CorpusAuditRow.id)
            .filter(CorpusAuditRow.source_sha256 == sha256)
            .one_or_none()
        )
        if existing is not None:
            return ("skip-duplicate", existing[0])

    try:
        report = parser(path)
    except LibreofficeMissing:
        return ("skip-no-libreoffice", None)
    except Exception as e:  # noqa: BLE001 — surfaces clean error to the caller
        return (f"error:{e.__class__.__name__}: {str(e)[:120]}", None)

    audit_row, sections = _report_to_rows(path, sha256, report)
    audit_row.sections = sections
    with session_scope() as s:
        s.add(audit_row)
        s.flush()
        new_id = audit_row.id
    return ("imported", new_id)


def ingest_directory(audit_dir: Path) -> dict[str, int]:
    """Ingest every supported file under `audit_dir`. Returns a status counter."""
    counts: dict[str, int] = {
        "imported": 0,
        "skip-duplicate": 0,
        "skip-format": 0,
        "skip-no-libreoffice": 0,
        "error": 0,
    }
    if not audit_dir.exists():
        return counts
    for path in sorted(p for p in audit_dir.iterdir() if p.is_file()):
        status, _ = ingest_file(path)
        bucket = status if status in counts else ("error" if status.startswith("error:") else "skip-format")
        counts[bucket] += 1
    return counts


__all__ = ["PARSERS", "ingest_file", "ingest_directory"]
