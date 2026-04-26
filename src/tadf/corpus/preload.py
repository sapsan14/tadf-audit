"""Preload historical audit reports under /audit/ into the database as draft Audits.

Each historical report becomes one Audit row, with:
  - composer/reviewer/building/client populated from the parsed cover
  - one Finding per parsed Section, observation_raw = body text (capped)
  - status = "draft" (these are reference imports, not freshly created)

The preload is idempotent: it skips if any audit with matching seq_no+year
already exists. Designed to be called on app startup when the DB is fresh AND
the /audit/ folder is present (i.e. local dev only — not Streamlit Cloud).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from tadf.corpus.parse_asice import parse_asice
from tadf.corpus.parse_docx import ParsedReport, parse_docx
from tadf.corpus.parse_pdf import parse_pdf
from tadf.db.orm import AuditRow
from tadf.db.repo import save_audit
from tadf.db.session import session_scope
from tadf.models import Audit, Auditor, Building, Client, Finding

PARSERS = {".docx": parse_docx, ".pdf": parse_pdf, ".asice": parse_asice}

# Filename examples in the corpus:
#   100825_TJ_AA-1-01_Auga_8_Narva-Joesuu_Audit_2025-08-10.pdf
#     -> seq=10, yy=08 (or seq=1, yy=00 — the date+work-nr encoding varies)
#   012026_EP_AA1-01_Energeetik...Audit_2026-01-20.docx
#   322025_EA_AA-1-01_PribreznoiAU..._Audit_25122025.doc
LEADING_SEQ_TYPE_RE = re.compile(r"^(?P<seq>\d{1,3})(?P<yy>\d{2})_(?P<type>[A-Z]{1,3})_")
# Trailing date — prefer ISO if present, else DDMMYYYY
TRAILING_DATE_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\D*$")
TRAILING_DATE_DMY_RE = re.compile(r"_(\d{2})(\d{2})(\d{4})\D*$")

SUBTYPE_KEYWORDS = {
    "kasutuseelne": ["kasutuseelne"],
    "erakorraline": ["erakorraline"],
    "korraline": ["korraline"],
}


def _infer_meta_from_filename(stem: str) -> dict:
    out: dict = {"seq_no": 1, "year": date.today().year, "type": "EA"}
    if m := LEADING_SEQ_TYPE_RE.match(stem):
        out["seq_no"] = int(m.group("seq"))
        out["type"] = m.group("type") or "EA"
        # 2-digit yy from leading prefix is the fallback if no trailing date
        yy = int(m.group("yy"))
        if 0 <= yy <= 99:
            out["year"] = 2000 + yy
    # Trailing date overrides year if present
    if m := TRAILING_DATE_ISO_RE.search(stem):
        out["year"] = int(m.group(1))
    elif m := TRAILING_DATE_DMY_RE.search(stem):
        out["year"] = int(m.group(3))
    return out


def _infer_subtype(report: ParsedReport, fallback: str = "kasutuseelne") -> str:
    haystack = (report.cover.audit_type or "").lower()
    haystack += " " + " ".join(s.title.lower() for s in report.sections[:5])
    for subtype, kws in SUBTYPE_KEYWORDS.items():
        if any(kw in haystack for kw in kws):
            return subtype
    return fallback


def _parse_visit_date(report: ParsedReport, fallback: date) -> date:
    if not report.cover.location_date:
        return fallback
    if m := re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", report.cover.location_date):
        d, mo, y = (int(m.group(i)) for i in (1, 2, 3))
        try:
            return date(y, mo, d)
        except ValueError:
            return fallback
    return fallback


def _section_to_finding(section, audit_id_placeholder=None) -> Finding | None:
    body = "\n".join(section.body).strip()
    if not body:
        return None
    # Cap at 4000 chars so a long section doesn't overwhelm the DB
    if len(body) > 4000:
        body = body[:4000] + "\n[…усечено при импорте]"
    return Finding(
        section_ref=section.number,
        severity="info",
        observation_raw=body,
        recommendation=None,
    )


def _report_to_audit(path: Path, report: ParsedReport) -> Audit:
    meta = _infer_meta_from_filename(path.stem)
    subtype = _infer_subtype(report)
    visit = _parse_visit_date(report, fallback=date(meta["year"], 1, 1))

    composer = Auditor(
        full_name=report.cover.composer_name or report.cover.reviewer_name or "—",
        company=report.cover.composer_company,
        company_reg_nr=report.cover.composer_reg_nr,
    )
    reviewer = Auditor(
        full_name=report.cover.reviewer_name or "Fjodor Sokolov",
        kutsetunnistus_no=report.cover.reviewer_kutsetunnistus or "148515",
        qualification=report.cover.reviewer_qualification or "Diplomeeritud insener tase 7",
        company="TADF Ehitus OÜ",
    )
    building = Building(
        address=report.cover.address or "(unknown)",
        ehr_code=report.cover.ehr_code,
        construction_year=None,
        substitute_docs_note=f"Импортировано из {path.name} — данные могут быть неполными",
    )
    client = Client(name=report.cover.client or "(импорт из архива)")

    findings: list[Finding] = []
    for s in report.sections:
        f = _section_to_finding(s)
        if f is not None:
            findings.append(f)

    # Ensure the §5 mandatory sections 11 and 14 each have at least one finding
    # so the imported audit can be re-rendered without immediately failing the
    # checklist. Use a placeholder pointing at the source.
    has_summary = any(f.section_ref.startswith("11") for f in findings)
    has_final = any(f.section_ref.startswith("14") for f in findings)
    if not has_summary:
        findings.append(
            Finding(
                section_ref="11",
                severity="info",
                observation_raw=(f"[Импортировано из {path.name}] Kokkuvõte: см. оригинал отчёта."),
            )
        )
    if not has_final:
        findings.append(
            Finding(
                section_ref="14",
                severity="info",
                observation_raw=(f"[Импортировано из {path.name}] Lõpphinnang: см. оригинал отчёта."),
            )
        )

    return Audit(
        seq_no=meta["seq_no"],
        year=meta["year"],
        type=meta["type"] if meta["type"] in ("EA", "EP", "TJ", "TP", "AU") else "EA",
        subtype=subtype,
        purpose=(
            f"Импортировано из исторического отчёта {path.name}. "
            "Это черновик для просмотра — отредактируйте перед использованием."
        ),
        scope="Импорт из архива — см. оригинал.",
        visit_date=visit,
        composer=composer,
        reviewer=reviewer,
        building=building,
        client=client,
        findings=findings,
    )


def preload_demo() -> int:
    """Insert hand-crafted demo audits if the DB has no audits.

    Used as the cloud-friendly seed (the /audit/ folder is gitignored, so on
    Streamlit Cloud `preload_corpus` finds nothing). Returns the number inserted.
    """
    from tadf.demo import all_demos

    inserted = 0
    with session_scope() as s:
        already = s.query(AuditRow).count()
    if already > 0:
        return 0
    for demo in all_demos():
        with session_scope() as s:
            save_audit(s, demo)
        inserted += 1
    return inserted


def preload_corpus(audit_dir: Path) -> tuple[int, int]:
    """Import all parseable reports from `audit_dir` into the database.

    Returns (imported, skipped). Idempotent: rows with matching (seq_no, year,
    address) are not duplicated.
    """
    if not audit_dir.exists():
        return 0, 0

    imported = skipped = 0
    with session_scope() as s:
        # Precompute existing keys to avoid duplicate imports on reruns
        existing = {
            (row.seq_no, row.year, (row.building.address or "")[:60]) for row in s.query(AuditRow).all()
        }

    for path in sorted(audit_dir.iterdir()):
        if not path.is_file():
            continue
        parser = PARSERS.get(path.suffix.lower())
        if parser is None:
            skipped += 1
            continue
        try:
            report = parser(path)
            audit = _report_to_audit(path, report)
        except Exception as e:
            print(f"  preload skip {path.name}: {e}")
            skipped += 1
            continue

        key = (audit.seq_no, audit.year, audit.building.address[:60])
        if key in existing:
            skipped += 1
            continue

        with session_scope() as s:
            save_audit(s, audit)
        imported += 1

    return imported, skipped
