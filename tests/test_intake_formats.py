"""Tests for tadf.intake.document_extract — file-format dispatch.

We don't exercise the LLM extractor here (it's covered in test_extractor.py);
this file makes sure the new .doc and .asice paths route correctly and that
the LibreOffice-missing case raises the sentinel exception cleanly.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from docx import Document

import tadf.corpus.parse_doc as parse_doc_module
import tadf.intake.document_extract as intake
from tadf.intake.document_extract import LibreofficeMissing, to_text


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_to_text_docx_passthrough():
    data = _make_docx_bytes(["Aadress: Auga 8", "Ehitusaasta: 2018"])
    text = to_text("project.docx", data)
    assert "Auga 8" in text
    assert "2018" in text


def test_to_text_unknown_extension_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        to_text("notes.txt", b"hello")


def test_to_text_doc_raises_libreoffice_missing(monkeypatch):
    """When soffice is absent, .doc must raise LibreofficeMissing — not a
    generic OSError — so the UI can show the install hint."""
    monkeypatch.setattr(parse_doc_module, "_find_soffice", lambda: None)
    # Also patch the symbol used inside intake (it imported _find_soffice
    # by reference at module load).
    monkeypatch.setattr(intake, "_find_soffice", lambda: None)
    with pytest.raises(LibreofficeMissing):
        to_text("legacy.doc", b"\xd0\xcf\x11\xe0fake-ole-header")


def test_to_text_asice_with_inner_docx():
    """ASiC-E containers wrap a single canonical document. We must locate the
    inner .docx and route it through the docx text path."""
    inner_docx = _make_docx_bytes(["Pindala: 75 m²", "Ehitusaasta: 1985"])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.etsi.asic-e+zip")
        z.writestr("META-INF/signatures.xml", "<sig/>")
        z.writestr("project.docx", inner_docx)
    asice_bytes = buf.getvalue()

    text = to_text("signed.asice", asice_bytes)
    assert "75 m" in text
    assert "1985" in text


def test_to_text_asice_with_inner_pdf(monkeypatch):
    """ASiC-E with PDF inside should hit the pdf path. We mock _pdf_to_text
    so the test doesn't depend on real PDF bytes."""
    monkeypatch.setattr(intake, "_pdf_to_text", lambda data: "PDF-TEXT")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.etsi.asic-e+zip")
        z.writestr("META-INF/signatures.xml", "<sig/>")
        z.writestr("report.pdf", b"%PDF-1.4 fake-bytes")
    asice_bytes = buf.getvalue()

    assert to_text("signed.asice", asice_bytes) == "PDF-TEXT"


def test_to_text_asice_with_no_supported_payload():
    """Reject ASiC-E containers that hold something other than docx/pdf/doc."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.etsi.asic-e+zip")
        z.writestr("META-INF/signatures.xml", "<sig/>")
        z.writestr("note.txt", b"plain text not allowed")
    with pytest.raises(ValueError, match="No .docx / .pdf / .doc payload"):
        to_text("weird.asice", buf.getvalue())


def test_to_text_asice_with_inner_doc_routes_via_libreoffice(monkeypatch):
    """When the ASiC-E payload is .doc, we must reach the doc path
    (and therefore LibreofficeMissing fires when soffice is absent)."""
    monkeypatch.setattr(parse_doc_module, "_find_soffice", lambda: None)
    monkeypatch.setattr(intake, "_find_soffice", lambda: None)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.etsi.asic-e+zip")
        z.writestr("META-INF/signatures.xml", "<sig/>")
        z.writestr("legacy.doc", b"\xd0\xcf\x11\xe0fake-ole")
    with pytest.raises(LibreofficeMissing):
        to_text("legacy_signed.asice", buf.getvalue())


def test_to_text_asice_with_real_corpus_file_if_available():
    """Smoke test against a real ASiC-E from the corpus, if present."""
    corpus = Path(__file__).resolve().parents[1] / "audit"
    candidate = corpus / "J. V. Jannseni tn 29aAUDIT.asice"
    if not candidate.exists():
        pytest.skip("Corpus .asice not present")
    text = to_text(candidate.name, candidate.read_bytes())
    assert len(text) > 100  # something extracted
