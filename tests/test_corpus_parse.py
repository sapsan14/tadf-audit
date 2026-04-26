from __future__ import annotations

from pathlib import Path

import pytest

from tadf.corpus.parse_docx import parse_docx

CORPUS = Path(__file__).resolve().parents[1] / "audit"
DOCX = CORPUS / "012026_EP_AA1-01_Energeetik2AÜ74Narva-Jõesuu_Audit_2026-01-20.docx"


@pytest.mark.skipif(not DOCX.exists(), reason="Corpus .docx not present")
def test_parse_corpus_docx_cover():
    r = parse_docx(DOCX)
    c = r.cover
    assert c.composer_name == "Aleksei Sholokhov"
    assert c.reviewer_name == "Fjodor Sokolov"
    assert c.reviewer_kutsetunnistus == "148515"
    assert c.ehr_code == "102032773"
    assert "Linna AÜ 1062" in c.address


@pytest.mark.skipif(not DOCX.exists(), reason="Corpus .docx not present")
def test_parse_corpus_docx_sections():
    r = parse_docx(DOCX)
    titles = [s.title.upper() for s in r.sections]
    # The corpus uses these exact (or close) headings — fail loudly if the
    # author's template drifts and the parser stops finding them.
    assert any("ÜLDOSA" in t for t in titles)
    assert any("OBJEKT" in t for t in titles)
    assert any("TULEKAITSE" in t for t in titles)
    assert any("KOKKUVÕTE" in t for t in titles)
    assert any("LÕPPHINNANG" in t for t in titles)
    assert any("ALLKIRJ" in t for t in titles)
