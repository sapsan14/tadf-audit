"""Page «📚 Корпус» — browse and grow the historical-audit training corpus.

Two functions:
  1. **Browse**: tabular view of all imported audits + drill-down into a
     single audit's sections. The same data the few-shot retrieval feeds
     into the drafter / polisher.
  2. **Upload**: drop a new DOCX / PDF / ASiC-E (or .doc, if LibreOffice
     is on PATH) into `data/uploads/corpus/`; we hash + parse + ingest
     into `corpus_audit` + `corpus_section`. Idempotent — re-uploading
     the same bytes is a no-op.

Hard rule (`AGENTS.md:85`): the read-only `/audit/` source folder is never
modified. Uploaded files land in `data/uploads/corpus/`, separate from
the canonical archive.
"""

from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import streamlit as st  # noqa: E402
from sqlalchemy import func  # noqa: E402

from tadf.config import DATA_DIR  # noqa: E402
from tadf.corpus.parse_doc import is_available as libreoffice_available  # noqa: E402
from tadf.corpus.store import ingest_file  # noqa: E402
from tadf.db.orm import CorpusAuditRow, CorpusClauseRow, CorpusSectionRow  # noqa: E402
from tadf.db.session import session_scope  # noqa: E402
from tadf.llm import is_available as llm_available  # noqa: E402
from tadf.llm.corpus_extractor import (  # noqa: E402
    extract_clauses_for_audit,
    has_extracted,
)

UPLOAD_DIR = DATA_DIR / "uploads" / "corpus"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

st.title("📚 Корпус — учебная база аудитов")

st.markdown(
    """
TADF учится на ваших старых аудитах. Каждый отчёт здесь — это эталон
стиля и формулировок, который ИИ (Claude сейчас, любой другой в будущем)
подмешивает в промпт как few-shot пример.

Данные хранятся в обычной SQLite-таблице (`corpus_audit` + `corpus_section`)
без какой-либо привязки к Claude. Если позже поменяете LLM-провайдера —
эти записи останутся пригодными как есть.

**Что не попадает в корпус как пример:** разделы 11 (Kokkuvõte) и
14 (Lõpphinnang) — только аудитор, без ИИ. Их тексты загружаются для
архивного просмотра, но никогда не идут в LLM-контекст.
"""
)

# ---------------------------------------------------------------------------
# 1. Загрузка нового аудита
# ---------------------------------------------------------------------------

st.subheader("Добавить новый аудит")

if not libreoffice_available():
    st.caption(
        "⚠️ LibreOffice (`soffice`) не найден на PATH — `.doc` файлы будут "
        "пропущены. Для поддержки legacy `.doc`: `apt-get install libreoffice`."
    )

uploaded = st.file_uploader(
    "Перетащите сюда `.docx` / `.pdf` / `.asice` (или `.doc`, если установлен LibreOffice)",
    type=["docx", "pdf", "asice", "doc"],
    accept_multiple_files=False,
    key="corpus_upload",
)

if uploaded is not None:
    safe_name = uploaded.name.replace("/", "_").replace("\\", "_")
    target = UPLOAD_DIR / safe_name
    target.write_bytes(uploaded.getvalue())
    with st.status(f"Парсинг и сохранение «{safe_name}»…", expanded=True) as status:
        status.write(f"Файл сохранён в `{target.relative_to(DATA_DIR.parent)}`")
        result, audit_id = ingest_file(target)
        if result == "imported":
            status.update(label=f"✅ Импортировано (id={audit_id})", state="complete")
            st.success(
                f"Аудит добавлен в корпус как запись #{audit_id}. "
                "Прокрутите ниже, чтобы посмотреть распознанные секции."
            )
        elif result == "skip-duplicate":
            status.update(label="↻ Дубликат (по SHA-256 содержимого)", state="complete")
            st.info(
                f"Файл с таким же содержимым уже есть в корпусе как запись #{audit_id}."
            )
        elif result == "skip-no-libreoffice":
            status.update(label="⚠️ Нужен LibreOffice", state="error")
            st.warning(
                "Это `.doc` файл; чтобы его распарсить, установите LibreOffice "
                "(`apt-get install libreoffice`)."
            )
        elif result == "skip-format":
            status.update(label="⚠️ Формат не поддерживается", state="error")
        else:
            status.update(label=f"❌ Ошибка: {result}", state="error")
            st.error(result)

st.divider()

# ---------------------------------------------------------------------------
# 2. Сводка по корпусу
# ---------------------------------------------------------------------------

with session_scope() as s:
    total_audits = s.query(func.count(CorpusAuditRow.id)).scalar() or 0
    total_sections = s.query(func.count(CorpusSectionRow.id)).scalar() or 0
    matched_sections = (
        s.query(func.count(CorpusSectionRow.id))
        .filter(CorpusSectionRow.section_ref.isnot(None))
        .scalar()
        or 0
    )

c1, c2, c3 = st.columns(3)
c1.metric("Аудитов в корпусе", total_audits)
c2.metric("Секций (всего)", total_sections)
c3.metric(
    "Привязано к canonical-разделам",
    matched_sections,
    f"{(matched_sections * 100 // total_sections) if total_sections else 0}%",
)

if total_audits == 0:
    st.info(
        "Корпус пуст. Запустите `uv run python scripts/ingest_corpus.py`, "
        "чтобы импортировать существующие отчёты из `/home/anton/projects/tadf/audit/`, "
        "или загрузите файл выше."
    )
    st.stop()

# ---------------------------------------------------------------------------
# 3. Таблица аудитов
# ---------------------------------------------------------------------------

st.subheader("Аудиты в корпусе")

with session_scope() as s:
    rows = (
        s.query(
            CorpusAuditRow.id,
            CorpusAuditRow.year,
            CorpusAuditRow.audit_kind,
            CorpusAuditRow.subtype,
            CorpusAuditRow.address,
            CorpusAuditRow.filename,
            CorpusAuditRow.source_format,
        )
        .order_by(CorpusAuditRow.year.desc().nulls_last(), CorpusAuditRow.id)
        .all()
    )
    section_counts = dict(
        s.query(CorpusSectionRow.audit_id, func.count(CorpusSectionRow.id))
        .group_by(CorpusSectionRow.audit_id)
        .all()
    )

table_data = [
    {
        "ID": r.id,
        "Год": r.year or "—",
        "Тип": r.audit_kind or "—",
        "Подтип": r.subtype or "—",
        "Формат": r.source_format,
        "Секций": section_counts.get(r.id, 0),
        "Адрес": (r.address or "—")[:60],
        "Файл": r.filename[:60],
    }
    for r in rows
]
st.dataframe(table_data, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# 4. Просмотр одного аудита
# ---------------------------------------------------------------------------

st.subheader("Посмотреть секции одного аудита")
audit_ids = [r.id for r in rows]
labels = {r.id: f"#{r.id} — {r.filename[:60]}" for r in rows}
chosen = st.selectbox(
    "Выбрать аудит",
    options=audit_ids,
    format_func=lambda i: labels[i],
    key="corpus_view_choice",
)

if chosen is not None:
    with session_scope() as s:
        a = s.get(CorpusAuditRow, chosen)
        if a is None:
            st.error("Запись не найдена.")
            st.stop()
        sections = (
            s.query(CorpusSectionRow)
            .filter(CorpusSectionRow.audit_id == chosen)
            .order_by(CorpusSectionRow.id)
            .all()
        )
        clauses_by_section: dict[int, list[CorpusClauseRow]] = {}
        for c in (
            s.query(CorpusClauseRow)
            .filter(CorpusClauseRow.audit_id == chosen)
            .order_by(CorpusClauseRow.section_id, CorpusClauseRow.id)
            .all()
        ):
            clauses_by_section.setdefault(c.section_id, []).append(c)

        # Detach for use after the session closes (read-only display).
        for sec in sections:
            s.expunge(sec)
        for cl_list in clauses_by_section.values():
            for cl in cl_list:
                s.expunge(cl)
        s.expunge(a)

    st.markdown(
        f"**{a.filename}**  ·  {a.source_format}  ·  "
        f"год {a.year or '—'}  ·  тип {a.audit_kind or '—'}  ·  "
        f"подтип {a.subtype or '—'}"
    )
    if a.address:
        st.caption(f"Адрес: {a.address}")
    if a.composer_name or a.composer_company:
        st.caption(
            f"Составитель: {a.composer_name or '—'} "
            f"({a.composer_company or '—'})"
        )
    st.caption(
        f"Источник: `{a.source_path}` · sha256={a.source_sha256[:12]}…"
    )

    # ---- LLM-дистилляция ----
    distilled_total = sum(len(v) for v in clauses_by_section.values())
    already_distilled = has_extracted(chosen) if llm_available() else False

    col_a, col_b = st.columns([3, 1])
    with col_a:
        if not llm_available():
            st.info(
                "🤖 ИИ-дистилляция выключена — нет ключа Anthropic. "
                "Заполните `ANTHROPIC_API_KEY`, чтобы извлечь типовые "
                "формулировки и шаблоны замечаний из этого аудита."
            )
        elif already_distilled:
            st.success(
                f"✅ Аудит дистиллирован: **{distilled_total}** "
                f"clauses готовы как few-shot для drafter / polish."
            )
        else:
            st.info(
                "ℹ️ Этот аудит ещё не дистиллирован. Дистилляция = разбор "
                "текста секций на типовые формулировки (boilerplate), "
                "паттерны замечаний (finding) и резюме (summary). Результат "
                "хранится в `corpus_clause` и используется как few-shot "
                "при генерации новых аудитов."
            )

    with col_b:
        if llm_available():
            distill_clicked = st.button(
                "🤖 Дистиллировать",
                key=f"distill_{chosen}",
                disabled=already_distilled,
                help=(
                    "Запустить ИИ-извлечение для всех секций аудита. "
                    "Локированные секции 11/14 пропускаются."
                ),
                type="primary" if not already_distilled else "secondary",
            )
            if distill_clicked:
                with st.status(
                    "Claude (Haiku 4.5) распарсивает секции…", expanded=True
                ) as status:
                    try:
                        counts = extract_clauses_for_audit(chosen)
                        status.update(
                            label=(
                                f"Готово ✅  "
                                f"clauses={counts['clauses_inserted']} "
                                f"sec={counts['sections_processed']}"
                            ),
                            state="complete",
                        )
                        st.success(
                            f"Извлечено: **{counts['clauses_inserted']}** "
                            f"clauses из {counts['sections_processed']} секций "
                            f"(пропущено locked={counts['skipped_locked']}, "
                            f"коротких={counts['skipped_short']})."
                        )
                    except Exception as e:  # noqa: BLE001
                        status.update(label="Ошибка ❌", state="error", expanded=True)
                        st.error(f"{type(e).__name__}: {e}")
                st.rerun()

    st.markdown(f"**Секций распознано: {len(sections)}**")
    for sec in sections:
        ref_label = (
            f"`{sec.raw_number}` → `{sec.section_ref}`"
            if sec.section_ref
            else f"`{sec.raw_number}` (canonical: —)"
        )
        sec_clauses = clauses_by_section.get(sec.id, [])
        clause_marker = f"  ·  ✨ {len(sec_clauses)} clauses" if sec_clauses else ""
        with st.expander(
            f"{ref_label}  ·  {sec.title[:80]}{clause_marker}", expanded=False
        ):
            if sec_clauses:
                st.markdown("**Дистиллированные clauses (для few-shot):**")
                for cl in sec_clauses:
                    badge = {
                        "boilerplate": "🧱 Boilerplate",
                        "finding": "🔍 Finding",
                        "summary": "📝 Summary",
                    }.get(cl.kind, cl.kind)
                    st.markdown(
                        f"- {badge} · reusability={cl.reusability:.2f} · "
                        f"model=`{cl.model}`"
                    )
                    st.text(cl.text)
                    if cl.recommendation:
                        st.caption(f"Soovitus: {cl.recommendation}")
                st.divider()

            st.markdown("**Сырой текст секции (parser output):**")
            st.text(sec.body_text[:4000])
            if len(sec.body_text) > 4000:
                st.caption(
                    f"…ещё {len(sec.body_text) - 4000} символов скрыты "
                    "(показаны первые 4000)."
                )
