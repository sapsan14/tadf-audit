"""Parse historical audit reports under /audit/ and persist them in two places:

1. JSON snapshots in `data/corpus/<stem>.json` (legacy artifact — kept for
   git-friendly review and offline diff). One file per parseable audit.
2. The `corpus_audit` + `corpus_section` SQL tables (new — the LLM-agnostic
   training corpus consumed by the few-shot retrieval helper).

Handles `.docx`, `.pdf`, `.asice`, and `.doc` (the last one needs LibreOffice
on PATH; gracefully skipped with a notice if `soffice` is unavailable).

Idempotent: re-running on the same files is a no-op for the DB (deduped by
SHA-256 of the file bytes); JSON snapshots are overwritten verbatim.
"""

from __future__ import annotations

import json
from pathlib import Path

from tadf.corpus.parse_doc import LibreofficeMissing
from tadf.corpus.parse_doc import is_available as libreoffice_available
from tadf.corpus.store import PARSERS, ingest_file

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "audit"
OUT_DIR = ROOT / "data" / "corpus"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not AUDIT_DIR.exists():
        print(f"No {AUDIT_DIR} folder — nothing to ingest.")
        return

    if not libreoffice_available():
        print(
            "  note: LibreOffice (soffice) not on PATH — .doc files will be "
            "skipped. Install libreoffice to ingest legacy .doc reports."
        )

    files = sorted(p for p in AUDIT_DIR.iterdir() if p.is_file())
    counts: dict[str, int] = {
        "imported": 0,
        "skip-duplicate": 0,
        "skip-format": 0,
        "skip-no-libreoffice": 0,
        "error": 0,
    }
    for src in files:
        ext = src.suffix.lower()
        parser = PARSERS.get(ext)
        if parser is None:
            print(f"  skip {src.name}  ({ext} not supported)")
            counts["skip-format"] += 1
            continue

        # Write the JSON snapshot first (cheap, useful even if DB ingest later
        # detects a duplicate). For .doc we must catch LibreofficeMissing here
        # so the snapshot step degrades the same way the DB step does.
        try:
            report = parser(src)
        except LibreofficeMissing:
            print(f"  skip {src.name}  (no libreoffice)")
            counts["skip-no-libreoffice"] += 1
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {src.name}  -> {e}")
            counts["error"] += 1
            continue

        out = OUT_DIR / f"{src.stem}.json"
        out.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # DB ingest is independent of the snapshot write — re-parses the file
        # but lets us reuse the dedup-by-sha256 logic in `store.ingest_file`.
        status, audit_id = ingest_file(src)
        bucket = status if status in counts else ("error" if status.startswith("error:") else "skip-format")
        counts[bucket] += 1
        marker = "ok" if status == "imported" else "dup" if status == "skip-duplicate" else "??"
        suffix = f"  -> {len(report.sections)} sections, db={status} (id={audit_id})"
        print(f"  {marker:3s}  {src.name}{suffix}")

    print(
        f"\nIngest summary: imported={counts['imported']} "
        f"duplicates={counts['skip-duplicate']} "
        f"skipped-format={counts['skip-format']} "
        f"skipped-no-libreoffice={counts['skip-no-libreoffice']} "
        f"errors={counts['error']}"
    )


if __name__ == "__main__":
    main()
