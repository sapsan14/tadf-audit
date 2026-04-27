"""Parse a legacy Word `.doc` (binary, pre-2007) by converting it to `.docx`
via headless LibreOffice and routing the result through `parse_docx`.

5 of the 12 historical reports in the corpus are `.doc`. LibreOffice is the
only realistic option: `python-docx` does not read binary `.doc`, and the
alternatives (`antiword`, `catdoc`) drop most formatting and are not in the
project's stack.

If `soffice` is not on PATH (e.g. local laptop without LibreOffice), we
raise `LibreofficeMissing` so the caller can skip the file with a clear
log line instead of crashing the whole ingest.

The Dockerfile already documents the apt-get install line for derived
images that need to run the corpus preload server-side.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from tadf.corpus.parse_docx import ParsedReport, parse_docx


class LibreofficeMissing(RuntimeError):
    """Raised when neither `soffice` nor `libreoffice` is available on PATH."""


def _find_soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def is_available() -> bool:
    return _find_soffice() is not None


def _convert_doc_to_docx(src: Path, out_dir: Path) -> Path:
    soffice = _find_soffice()
    if soffice is None:
        raise LibreofficeMissing(
            "soffice/libreoffice not found on PATH. Install LibreOffice to "
            "ingest legacy .doc files (apt-get install libreoffice on Debian/"
            "Ubuntu). On Hetzner: see Dockerfile for the documented one-line "
            "addition to the derived image."
        )
    proc = subprocess.run(
        [soffice, "--headless", "--convert-to", "docx", "--outdir", str(out_dir), str(src)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"LibreOffice failed to convert {src.name}: rc={proc.returncode} "
            f"stderr={proc.stderr.strip()[:200]}"
        )
    converted = out_dir / (src.stem + ".docx")
    if not converted.exists():
        raise RuntimeError(
            f"LibreOffice reported success but {converted} is missing; "
            f"stdout={proc.stdout.strip()[:200]}"
        )
    return converted


def parse_doc(path: str | Path) -> ParsedReport:
    src = Path(path)
    with tempfile.TemporaryDirectory(prefix="tadf-doc-") as tmp:
        converted = _convert_doc_to_docx(src, Path(tmp))
        report = parse_docx(converted)
    # Keep the original .doc as the canonical source path.
    report.source_path = str(src)
    return report
