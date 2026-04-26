"""Parse an ASiC-E (.asice) signed container by extracting the inner PDF/DOCX."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from tadf.corpus.parse_docx import ParsedReport, parse_docx
from tadf.corpus.parse_pdf import parse_pdf


def parse_asice(path: str | Path) -> ParsedReport:
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        # Find the document inside (skip META-INF, mimetype, signatures*.xml)
        candidates = [
            n
            for n in z.namelist()
            if not n.startswith("META-INF/") and not n.lower().endswith(".xml") and n != "mimetype"
        ]
        # Prefer PDF, then DOCX
        chosen = next((c for c in candidates if c.lower().endswith(".pdf")), None)
        if chosen is None:
            chosen = next((c for c in candidates if c.lower().endswith(".docx")), None)
        if chosen is None:
            raise ValueError(f"No PDF or DOCX found inside {path}")

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(chosen).suffix) as tmp:
            tmp.write(z.read(chosen))
            tmp_path = Path(tmp.name)

    try:
        report = parse_pdf(tmp_path) if tmp_path.suffix.lower() == ".pdf" else parse_docx(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Replace the temp source path with the original .asice path
    report.source_path = str(path)
    return report
