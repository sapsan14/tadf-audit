"""Parse historical audit reports under /audit/ into JSON snapshots in data/corpus/.

Phase 1 only handles .docx (the one canonical modern report). Legacy .doc, PDF
and .asice ingestion is added in later phases (LibreOffice + pdfplumber + zipfile).
"""

from __future__ import annotations

import json
from pathlib import Path

from tadf.corpus.parse_docx import parse_docx

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "audit"
OUT_DIR = ROOT / "data" / "corpus"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    docx_files = sorted(AUDIT_DIR.glob("*.docx"))
    if not docx_files:
        print(f"No .docx files in {AUDIT_DIR}")
        return

    for src in docx_files:
        report = parse_docx(src)
        out = OUT_DIR / f"{src.stem}.json"
        out.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  wrote {out.relative_to(ROOT)}  ({len(report.sections)} sections)")

    print(f"\nIngested {len(docx_files)} .docx report(s) into {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
