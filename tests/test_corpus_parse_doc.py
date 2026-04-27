"""Tests for tadf.corpus.parse_doc — graceful skip when LibreOffice is absent."""

from __future__ import annotations

import pytest

import tadf.corpus.parse_doc as parse_doc
from tadf.corpus.parse_doc import LibreofficeMissing, is_available
from tadf.corpus.parse_doc import parse_doc as parse_doc_fn


def test_is_available_returns_bool():
    assert isinstance(is_available(), bool)


def test_parse_doc_raises_when_soffice_missing(tmp_path, monkeypatch):
    """If `soffice`/`libreoffice` is not on PATH, the parser must raise the
    sentinel LibreofficeMissing — not crash with a generic FileNotFoundError —
    so the ingest pipeline can skip cleanly."""
    monkeypatch.setattr(parse_doc, "_find_soffice", lambda: None)

    fake = tmp_path / "fake.doc"
    fake.write_bytes(b"not really a doc")
    with pytest.raises(LibreofficeMissing):
        parse_doc_fn(fake)
