"""Distil a corpus section into reusable clauses.

Reads the raw `body_text` of a `CorpusSectionRow` and asks Claude (Haiku 4.5)
to split it into three kinds of typed records that the few-shot retrieval
pipeline can serve:

  - `boilerplate` — generic standing formulations
  - `finding`     — observation + recommendation pair
  - `summary`     — one-paragraph "what this section is actually about"

Hard rules:
  - Sections 11 (Kokkuvõte) and 14 (Lõpphinnang) are **never** distilled.
    They are auditor-only by both legal convention and TADF policy
    (`AGENTS.md:79`); leaking distilled boilerplate from them would defeat
    the lock that keeps drafter / polish out of those sections.
  - Re-running on the same section is a no-op while the schema_version
    matches: existing rows for that (section_id, model, schema_version)
    block fresh inserts. To re-extract with a different model, change the
    `model` argument.

Schema design choice: the output table (`corpus_clause`) holds plain text
plus reusability score and source metadata — nothing Claude-specific.
A future LLM swap reuses the same table; we'd simply rerun the extractor
and tag rows with the new provider in the `model` column.
"""

from __future__ import annotations

from typing import Any

from tadf.db.orm import CorpusClauseRow, CorpusSectionRow
from tadf.db.session import session_scope
from tadf.llm.client import MODEL_RANKER, complete_json

SCHEMA_VERSION = 1
LOCKED_TOP_LEVELS = {"11", "14"}

_VALID_KINDS = {"boilerplate", "finding", "summary"}

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "clauses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["boilerplate", "finding", "summary"],
                    },
                    "text": {"type": "string"},
                    "recommendation": {"type": ["string", "null"]},
                    "reusability": {"type": "number"},
                },
                "required": ["kind", "text", "recommendation", "reusability"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clauses"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "Sa loed Eesti ehitise auditi aruande ühe jaotise teksti. Sinu ülesanne — "
    "eraldada sellest taaskasutatavad lõigud, mida saab hilisemate auditite "
    "kirjutamisel few-shot näidetena kasutada. Kõik valjundi tekst peab olema "
    "puhtas eesti keeles.\n\n"
    "Tagasta JSON skeemi järgi, kus iga clause on üks järgmistest tüüpidest:\n\n"
    "1. `boilerplate` — üldised tüüplaused / standardsõnastused, mis korduvad "
    "auditite vahel sarnasel kujul (nt 'Auditi viidi läbi vastavalt EVS 812-7 "
    "nõuetele.'). NIVELLEERI projekti spetsiifilised andmed (aastad, mõõdud, "
    "konkreetsed nimed) — anna mall, mitte tsitaat.\n\n"
    "2. `finding` — konkreetne tähelepanek koos soovitusega. `text` = vaatluse "
    "kirjeldus, `recommendation` = soovitatav tegevus (kui see oli sõnastatud, "
    "muidu null). Säilita technical-context, sest sarnases hoones võib seesama "
    "leid uuesti tekkida.\n\n"
    "3. `summary` — üks lõik (2–4 lauset), mis kirjeldab millest see jaotis "
    "selles auditiaruandes räägib (mitte mida üldiselt jaotis sisaldab).\n\n"
    "Igale clausele anna `reusability` 0..1: kui geneeriline / mall-laadne "
    "see on (1 = puhas mall, sobib igale auditile; 0 = väga konkreetne, "
    "sobib ainult sellele hoonele). Boilerplate-tüüpilisel ei tohi see olla "
    "alla 0.6, finding tavaliselt 0.2..0.6, summary 0.1..0.3.\n\n"
    "Kui jaotis on liiga lühike, tühi või puhttehniline tabeliviide, "
    "tagasta `clauses: []`. Ära mõtle välja sisu, mida tekstis pole.\n\n"
    "Vasta AINULT JSON-iga, mis vastab antud skeemile."
)


def _is_locked(section_ref: str | None) -> bool:
    if section_ref is None:
        return False
    return section_ref.split(".", 1)[0] in LOCKED_TOP_LEVELS


def _normalise_clause(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Best-effort cleanup. Drops invalid kinds, clamps reusability, trims
    obvious whitespace. Returns None if the row is unusable."""
    kind = str(raw.get("kind", "")).strip().lower()
    if kind not in _VALID_KINDS:
        return None
    text = str(raw.get("text", "")).strip()
    if len(text) < 10:
        return None
    rec = raw.get("recommendation")
    rec = str(rec).strip() if rec else None
    if rec == "":
        rec = None
    if kind != "finding":
        # Recommendation only makes sense alongside a finding.
        rec = None
    try:
        reusability = float(raw.get("reusability", 0.5))
    except (TypeError, ValueError):
        reusability = 0.5
    reusability = max(0.0, min(1.0, reusability))
    return {
        "kind": kind,
        "text": text,
        "recommendation": rec,
        "reusability": reusability,
    }


def extract_clauses_for_section(
    section_id: int,
    *,
    model: str = MODEL_RANKER,
    force: bool = False,
) -> int:
    """Distil one corpus section into clauses and persist them.

    Returns the number of new rows inserted. Idempotent: rows for the
    same `(section_id, model, schema_version)` are not duplicated unless
    `force=True` is set (in which case existing rows are deleted first).

    Skips locked sections (11 / 14) silently — returns 0.
    Skips empty / very short bodies — returns 0.
    """
    with session_scope() as s:
        section = s.get(CorpusSectionRow, section_id)
        if section is None:
            raise ValueError(f"corpus_section #{section_id} not found")
        if _is_locked(section.section_ref):
            return 0
        body = (section.body_text or "").strip()
        if len(body) < 80:
            return 0
        existing = (
            s.query(CorpusClauseRow)
            .filter(
                CorpusClauseRow.section_id == section_id,
                CorpusClauseRow.model == model,
                CorpusClauseRow.schema_version == SCHEMA_VERSION,
            )
            .all()
        )
        if existing and not force:
            return 0
        if existing and force:
            for row in existing:
                s.delete(row)
            s.flush()

        # Capture identifying fields before we leave the session — the LLM
        # call might be slow and we don't want to hold the SQLite write
        # lock open for a multi-second API round-trip.
        audit_id = section.audit_id
        section_ref = section.section_ref
        title = section.title

    user = (
        f"Jaotis: {section_ref or '(canonical refita)'} — {title}\n\n"
        f"--- TEKST ---\n{body[:8000]}\n--- LÕPP ---"
    )
    data = complete_json(
        model=model,
        system=_SYSTEM_PROMPT,
        user=user,
        schema=_OUTPUT_SCHEMA,
        max_tokens=2500,
    )
    raw_clauses = data.get("clauses") if isinstance(data, dict) else None
    if not isinstance(raw_clauses, list):
        return 0

    inserted = 0
    with session_scope() as s:
        for raw in raw_clauses:
            if not isinstance(raw, dict):
                continue
            cleaned = _normalise_clause(raw)
            if cleaned is None:
                continue
            s.add(
                CorpusClauseRow(
                    audit_id=audit_id,
                    section_id=section_id,
                    section_ref=section_ref,
                    kind=cleaned["kind"],
                    text=cleaned["text"],
                    recommendation=cleaned["recommendation"],
                    reusability=cleaned["reusability"],
                    model=model,
                    schema_version=SCHEMA_VERSION,
                )
            )
            inserted += 1
    return inserted


def extract_clauses_for_audit(
    audit_id: int,
    *,
    model: str = MODEL_RANKER,
    force: bool = False,
) -> dict[str, int]:
    """Distil every (non-locked) section of an audit. Returns a counter
    `{"sections_processed": N, "clauses_inserted": M, "skipped_locked": K,
    "skipped_short": L}`.
    """
    with session_scope() as s:
        section_ids = [
            row.id
            for row in s.query(CorpusSectionRow)
            .filter(CorpusSectionRow.audit_id == audit_id)
            .all()
        ]

    counts = {
        "sections_processed": 0,
        "clauses_inserted": 0,
        "skipped_locked": 0,
        "skipped_short": 0,
    }
    for sid in section_ids:
        # Pre-check locked / short to keep the counters informative without
        # a full LLM call for sections we will skip anyway.
        with session_scope() as s:
            sec = s.get(CorpusSectionRow, sid)
            if sec is None:
                continue
            if _is_locked(sec.section_ref):
                counts["skipped_locked"] += 1
                continue
            if len((sec.body_text or "").strip()) < 80:
                counts["skipped_short"] += 1
                continue
        n = extract_clauses_for_section(sid, model=model, force=force)
        counts["sections_processed"] += 1
        counts["clauses_inserted"] += n
    return counts


# Helpful when re-using this from the UI without importing the whole module.
def has_extracted(audit_id: int, *, model: str = MODEL_RANKER) -> bool:
    """True if any clause exists for this audit at the current schema_version."""
    with session_scope() as s:
        return (
            s.query(CorpusClauseRow.id)
            .filter(
                CorpusClauseRow.audit_id == audit_id,
                CorpusClauseRow.model == model,
                CorpusClauseRow.schema_version == SCHEMA_VERSION,
            )
            .first()
            is not None
        )


__all__ = [
    "SCHEMA_VERSION",
    "extract_clauses_for_audit",
    "extract_clauses_for_section",
    "has_extracted",
]
