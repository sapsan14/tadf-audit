"""Convert an uploaded project document (DOCX/PDF) to plain text and run
it through the Building extractor.

Public entry point: `extract_from_upload(uploaded_file) -> (extracted_dict, raw_text)`.
The raw_text is returned alongside the extraction so the UI can show
Fjodor what Claude actually saw (debug expander).
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

from tadf.llm.extractor import extract_building


class _UploadedFile(Protocol):
    """Subset of streamlit.UploadedFile / file-like."""

    name: str

    def read(self) -> bytes: ...


def _docx_to_text(data: bytes) -> str:
    """Concatenate every paragraph in a .docx file. Project explanatory
    notes don't follow the §5 audit outline, so we skip the heading-aware
    heuristics in `corpus/parse_docx.py` and just take everything."""
    from docx import Document

    doc = Document(BytesIO(data))
    parts: list[str] = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t:
            parts.append(t)
    # Tables often hold the most structured data (year, area, etc.) in
    # explanatory notes — flatten them.
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _pdf_to_text(data: bytes) -> str:
    """Concatenate every page's text in a .pdf via pdfplumber."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(BytesIO(data)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            t = t.strip()
            if t:
                parts.append(t)
    return "\n".join(parts)


def to_text(name: str, data: bytes) -> str:
    """Detect file type by extension, return plain text. Raises ValueError
    on unsupported types."""
    ext = Path(name).suffix.lower()
    if ext == ".docx":
        return _docx_to_text(data)
    if ext == ".pdf":
        return _pdf_to_text(data)
    raise ValueError(f"Unsupported file type: {ext} (only .docx and .pdf)")


def extract_from_upload(uploaded_file: _UploadedFile) -> tuple[dict[str, Any], str]:
    """Read the file, convert to text, run extractor. Returns
    (extracted_dict, raw_text)."""
    data = uploaded_file.read()
    text = to_text(uploaded_file.name, data)
    extracted = extract_building(text)
    return extracted, text


__all__ = ["extract_from_upload", "to_text"]
