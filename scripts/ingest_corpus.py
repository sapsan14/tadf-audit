"""Parse historical audit reports under /audit/ into JSON snapshots in data/corpus/.

Handles .docx, .pdf and .asice. Legacy .doc requires LibreOffice (not assumed
installed) and is skipped with a notice.
"""

from __future__ import annotations

import json
from pathlib import Path

from tadf.corpus.parse_asice import parse_asice
from tadf.corpus.parse_docx import parse_docx
from tadf.corpus.parse_pdf import parse_pdf

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "audit"
OUT_DIR = ROOT / "data" / "corpus"

PARSERS = {".docx": parse_docx, ".pdf": parse_pdf, ".asice": parse_asice}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not AUDIT_DIR.exists():
        print(f"No {AUDIT_DIR} folder — nothing to ingest.")
        return

    files = sorted(AUDIT_DIR.iterdir())
    parsed = skipped = 0
    for src in files:
        if not src.is_file():
            continue
        ext = src.suffix.lower()
        parser = PARSERS.get(ext)
        if parser is None:
            print(f"  skip {src.name}  ({ext} not supported in Phase 1)")
            skipped += 1
            continue
        try:
            report = parser(src)
        except Exception as e:
            print(f"  ERR  {src.name}  → {e}")
            skipped += 1
            continue
        out = OUT_DIR / f"{src.stem}.json"
        out.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  ok   {src.name}  → {len(report.sections)} sections")
        parsed += 1

    print(f"\nIngested {parsed} report(s), skipped {skipped}.")


if __name__ == "__main__":
    main()
