"""Few-shot retrieval over the historical corpus.

Pulls 0-N section bodies from `corpus_section` that match the section the
auditor is currently working on, so the drafter / polisher / captioner can
prepend them to its prompt as in-context examples.

Design choices:
- **No embeddings.** The corpus has 12 audits; lexical filter on
  `section_ref` + `subtype` is plenty. Embedding-based retrieval can be
  added later as a `tadf.llm.fewshot_dense` swap-in without touching
  call sites.
- **Provider-agnostic.** Returns plain Estonian text. A future GPT/Gemini
  client reuses the same function unchanged.
- **Sections 11 + 14 are excluded.** They are auditor-only by hard rule
  (`AGENTS.md:79`); leaking historical Kokkuvõte / Lõpphinnang into LLM
  context would defeat the lock.
- **Length cap.** Each example is trimmed to ~800 chars (≈ 1 paragraph)
  to keep the prompt budget under a few thousand input tokens even with
  two examples.
"""

from __future__ import annotations

from sqlalchemy import or_

from tadf.db.orm import CorpusAuditRow, CorpusClauseRow, CorpusSectionRow
from tadf.db.session import session_scope

# Hard-locked sections — never expose historical text from these to the LLM.
_LOCKED_TOP_LEVELS = {"11", "14"}

# Reasonable default per-example length. Long enough to preserve a coherent
# paragraph, short enough that two examples fit comfortably in the prompt
# alongside the auditor's input.
_DEFAULT_MAX_CHARS = 800


def _is_locked(section_ref: str | None) -> bool:
    if section_ref is None:
        return False
    return section_ref.split(".", 1)[0] in _LOCKED_TOP_LEVELS


def _trim(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    # Cut at a sentence/paragraph boundary if one is close to the limit.
    cut = text.rfind(". ", 0, max_chars)
    if cut > max_chars // 2:
        return text[: cut + 1]
    return text[:max_chars] + "…"


def _distilled_examples(
    section_ref: str,
    subtype: str | None,
    max_examples: int,
    max_chars: int,
) -> list[str]:
    """Pull distilled clauses (boilerplate + finding) from `corpus_clause`,
    preferring high-reusability rows. Returns formatted plain-text strings
    ready to drop into a few-shot block. Empty list if extractor hasn't
    run for this section or no clauses meet the reusability bar."""
    top_level = section_ref.split(".", 1)[0]
    out: list[str] = []
    seen: set[int] = set()

    def _format(row: CorpusClauseRow) -> str:
        head = "Tüüplause" if row.kind == "boilerplate" else "Leid"
        text = _trim(row.text, max_chars)
        if row.kind == "finding" and row.recommendation:
            rec = _trim(row.recommendation, max(120, max_chars // 3))
            return f"{head}: {text}\nSoovitus: {rec}"
        return f"{head}: {text}"

    def _collect(query) -> None:
        for row in query.limit(max_examples * 3).all():
            if row.id in seen:
                continue
            seen.add(row.id)
            out.append(_format(row))
            if len(out) >= max_examples:
                return

    with session_scope() as s:
        base = (
            s.query(CorpusClauseRow)
            .join(CorpusAuditRow, CorpusClauseRow.audit_id == CorpusAuditRow.id)
            .filter(
                CorpusClauseRow.kind.in_(("boilerplate", "finding")),
                CorpusClauseRow.reusability >= 0.5,
            )
            .order_by(CorpusClauseRow.reusability.desc(), CorpusClauseRow.id)
        )

        # 1. Exact ref + subtype match (best targeting)
        if subtype:
            _collect(
                base.filter(
                    CorpusClauseRow.section_ref == section_ref,
                    CorpusAuditRow.subtype == subtype,
                )
            )
        # 2. Exact ref, any subtype
        if len(out) < max_examples:
            _collect(base.filter(CorpusClauseRow.section_ref == section_ref))
        # 3. Top-level fallback
        if len(out) < max_examples:
            _collect(
                base.filter(
                    or_(
                        CorpusClauseRow.section_ref == top_level,
                        CorpusClauseRow.section_ref.like(f"{top_level}.%"),
                    )
                )
            )
    return out[:max_examples]


def examples_for(
    section_ref: str,
    *,
    subtype: str | None = None,
    max_examples: int = 2,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> list[str]:
    """Return up to `max_examples` corpus examples relevant to `section_ref`.

    Two-tier source:
      A. **Distilled clauses** from `corpus_clause` (when the LLM extractor
         has run for this section). These are tighter and more reusable.
      B. **Raw section bodies** as fallback when no distilled clauses are
         available — preserves the original behaviour from before the
         extractor existed.

    Selection order within each tier:
      1. Exact `section_ref` match, same subtype if `subtype` is given.
      2. Exact `section_ref` match, any subtype.
      3. Same top-level (e.g. "6.1" -> "6", "6.x"), same subtype.
      4. Same top-level, any subtype.

    Returns plain text snippets, each capped at `max_chars`. Empty list if
    no corpus is loaded, no matches, or the section is locked.
    """
    if max_examples <= 0 or _is_locked(section_ref):
        return []

    top_level = section_ref.split(".", 1)[0]
    if top_level in _LOCKED_TOP_LEVELS:
        return []

    # Tier A: distilled clauses, when the extractor has run.
    distilled = _distilled_examples(section_ref, subtype, max_examples, max_chars)
    if len(distilled) >= max_examples:
        return distilled

    # Tier B: raw bodies fill the remaining slots so partial extractor coverage
    # still produces `max_examples` total whenever the corpus has anything.
    seen_ids: set[int] = set()
    results: list[str] = list(distilled)

    def _collect(query) -> None:
        for row in query.limit(max_examples * 2).all():
            if row.id in seen_ids:
                continue
            seen_ids.add(row.id)
            body = _trim(row.body_text, max_chars)
            if not body:
                continue
            results.append(body)
            if len(results) >= max_examples:
                return

    with session_scope() as s:
        base = (
            s.query(CorpusSectionRow)
            .join(CorpusAuditRow, CorpusSectionRow.audit_id == CorpusAuditRow.id)
        )

        # 1. Exact ref + same subtype
        if subtype:
            q1 = base.filter(
                CorpusSectionRow.section_ref == section_ref,
                CorpusAuditRow.subtype == subtype,
            )
            _collect(q1)
        # 2. Exact ref, any subtype
        if len(results) < max_examples:
            q2 = base.filter(CorpusSectionRow.section_ref == section_ref)
            _collect(q2)
        # 3-4. Top-level fallback
        if len(results) < max_examples:
            q3 = base.filter(
                or_(
                    CorpusSectionRow.section_ref == top_level,
                    CorpusSectionRow.section_ref.like(f"{top_level}.%"),
                )
            )
            if subtype:
                q3_subtype = q3.filter(CorpusAuditRow.subtype == subtype)
                _collect(q3_subtype)
            if len(results) < max_examples:
                _collect(q3)

    return results[:max_examples]


def format_for_prompt(examples: list[str]) -> str:
    """Render a list of examples as an Estonian preface block ready to
    prepend to the user message of a drafter / polisher call. Returns empty
    string if no examples — call sites can unconditionally concatenate."""
    if not examples:
        return ""
    parts = ["Sarnaste jaotiste näited varasematest auditiaruannetest "
             "(jäljenda stiili, mitte fakte):"]
    for i, ex in enumerate(examples, 1):
        parts.append(f"\n--- Näide {i} ---\n{ex}")
    parts.append("\n--- Näited lõppevad ---\n")
    return "\n".join(parts)


__all__ = ["examples_for", "format_for_prompt"]
