from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import streamlit as st  # noqa: E402

from app._state import get_current, set_current  # noqa: E402
from app._widgets import flush_improve_pending, improve_button_for  # noqa: E402
from tadf.legal.loader import for_section  # noqa: E402
from tadf.llm import (  # noqa: E402
    draft_narrative,
    is_locked,
    polish_text,
    rank_legal_refs,
)
from tadf.llm import (  # noqa: E402
    is_available as llm_available,
)
from tadf.models import Finding  # noqa: E402
from tadf.sections import SECTION_KEYS, SECTION_LABELS  # noqa: E402

flush_improve_pending()

st.title("Наблюдения")
st.caption(
    "Выбор раздела опирается на структуру 14-секционного отчёта (Tiitelleht → "
    "Allkirjad). Подразделы (6.1–6.15, 7.1–7.10, 8.1–8.13 и т.д.) добавлены "
    "из стандартов EVS 812-7 / EVS 932 и из ваших старых отчётов."
)

audit = get_current()
scope = audit.id or "new"
llm_on = llm_available()

# Persistent error slot — errors survive st.rerun() and stay visible until the
# user dismisses them. Without this, an exception inside an LLM call flashes
# for one frame and disappears.
ERROR_KEY = f"_ai_error_{scope}"
if ERROR_KEY in st.session_state:
    err_msg = st.session_state[ERROR_KEY]
    with st.container(border=True):
        if "credit balance" in err_msg.lower():
            st.error(
                "💳 Недостаточно средств на счёте Anthropic API. "
                "Пополните баланс на https://console.anthropic.com → Plans & Billing."
            )
            with st.expander("Подробности ошибки"):
                st.code(err_msg, language=None)
        else:
            st.error(f"🤖❌ Ошибка ИИ: {err_msg}")
        if st.button("Закрыть", key=f"close_err_{scope}"):
            del st.session_state[ERROR_KEY]
            st.rerun()


def _record_error(prefix: str, e: Exception) -> None:
    """Stash the error in session_state so it survives the next st.rerun()."""
    st.session_state[ERROR_KEY] = f"{prefix}: {type(e).__name__}: {e}"


def _clear_error() -> None:
    st.session_state.pop(ERROR_KEY, None)

if not llm_on:
    st.info(
        "💡 ИИ-помощник (черновики, polish, ссылки на закон) сейчас выключен — "
        "нет ключа Anthropic. Можно работать вручную; ИИ-кнопки появятся, "
        "когда ключ будет настроен (см. README → ANTHROPIC_API_KEY)."
    )
else:
    st.info(
        "🤖 **Где находится ИИ-помощник:**\n"
        "- ✨ **Черновик из тезисов** — в раскрывающемся блоке ниже\n"
        "- ✏️ **Polish текста** — внутри каждого существующего наблюдения (раскройте её)\n"
        "- 💡 **Подобрать ссылки на закон** — там же, внутри наблюдения\n"
        "- 🤖 **Подпись к фото** — на странице «Фото»\n\n"
        "Все ответы ИИ показываются с кнопками «Принять / Отклонить» — без вашего "
        "согласия ничего в отчёт не попадает. Разделы 11 (Kokkuvõte) и 14 "
        "(Lõpphinnang) — только Вы пишете, ИИ для них недоступен."
    )

SEVERITY_OPTIONS = ["info", "nonconf_minor", "nonconf_major", "hazard"]
SEVERITY_LABELS = {
    "info": "📝 Инфо",
    "nonconf_minor": "⚠️ Мелкое несоответствие",
    "nonconf_major": "❗ Существенное несоответствие",
    "hazard": "🛑 Опасность",
}
SEVERITY_HELP = (
    "📝 Инфо — нейтральное наблюдение, нет нарушений\n"
    "⚠️ Мелкое несоответствие — отклонение от нормы, не угрожает безопасности\n"
    "❗ Существенное несоответствие — нарушение требований Ehitusseadustik / EVS, "
    "требуется устранение\n"
    "🛑 Опасность — непосредственная угроза жизни/здоровью, требуется немедленное "
    "действие (упоминается в Lõpphinnang)"
)


def _legal_refs_for(section_ref: str) -> list:
    return for_section(section_ref.split(".")[0], audit.type)


# ---------------------------------------------------------------------------
# AI scratchpad — bullets → formal Estonian narrative
# ---------------------------------------------------------------------------
NEW_SECTION_KEY = f"new_finding_section_{scope}"
NEW_OBS_KEY = f"new_finding_obs_{scope}"
NEW_SEV_KEY = f"new_finding_severity_{scope}"
DRAFT_RESULT_KEY = f"_draft_result_{scope}"


# Cross-audit "last used" defaults. After «➕ Добавить наблюдение» the most
# recent section/severity get stashed here so the next new-finding form on
# this OR a subsequent audit starts from where the auditor left off (matches
# the natural 6.1 → 6.2 → 6.3 progression of a structural walkthrough).
_LAST_SECTION_KEY = "_last_used_finding_section"
_LAST_SEVERITY_KEY = "_last_used_finding_severity"


def _ensure_new_finding_state() -> None:
    if NEW_SECTION_KEY not in st.session_state:
        st.session_state[NEW_SECTION_KEY] = st.session_state.get(
            _LAST_SECTION_KEY, SECTION_KEYS[0]
        )
    if NEW_OBS_KEY not in st.session_state:
        st.session_state[NEW_OBS_KEY] = ""
    if NEW_SEV_KEY not in st.session_state:
        st.session_state[NEW_SEV_KEY] = st.session_state.get(
            _LAST_SEVERITY_KEY, "info"
        )


_ensure_new_finding_state()

if llm_on:
    with st.expander("✨ ИИ-черновик: тезисы → формальный эстонский", expanded=False):
        st.caption(
            "Введите короткие тезисы — Claude развернёт их в формальный "
            "параграф для отчёта. Разделы 11 и 14 — только Вы (без ИИ)."
        )
        scratch_section = st.selectbox(
            "Раздел",
            options=SECTION_KEYS,
            format_func=lambda x: SECTION_LABELS[x],
            key=f"scratch_section_{scope}",
        )
        scratch_bullets = st.text_area(
            "Тезисы (на эстонском или русском)",
            height=100,
            key=f"scratch_bullets_{scope}",
        )
        st.caption(
            "💡 После ввода тезисов нажмите Tab или кликните вне поля — "
            "Streamlit сохраняет значение по уходу с поля, потом жмите кнопку."
        )
        scratch_clicked = st.button(
            "✨ Расширить тезисы",
            disabled=is_locked(scratch_section),
            key=f"scratch_run_{scope}",
            help=(
                "Sections 11/14 заблокированы. "
                "Для остальных — Sonnet 4.6 раскроет тезисы в один параграф."
            ),
        )
        if scratch_clicked and not scratch_bullets.strip():
            st.error("Введите тезисы перед запуском.")
        elif scratch_clicked:
            with st.status(
                "Claude (Sonnet 4.6) составляет эстонский черновик…",
                expanded=True,
            ) as status:
                st.write(f"Раздел: **{SECTION_LABELS.get(scratch_section, scratch_section)}**")
                st.write(f"Длина тезисов: {len(scratch_bullets)} символов")
                try:
                    draft = draft_narrative(scratch_section, scratch_bullets)
                    st.session_state[DRAFT_RESULT_KEY] = (scratch_section, draft)
                    _clear_error()
                    status.update(label="Готово ✅", state="complete", expanded=False)
                except Exception as e:
                    _record_error("Не удалось получить черновик", e)
                    status.update(label="Ошибка ❌", state="error", expanded=True)
            st.rerun()

# Show draft result with accept/reject
if DRAFT_RESULT_KEY in st.session_state:
    sec, draft = st.session_state[DRAFT_RESULT_KEY]
    st.success(f"Черновик от ИИ для раздела «{SECTION_LABELS.get(sec, sec)}»:")
    st.markdown(f"> {draft}")
    a, b = st.columns(2)
    if a.button("✅ Использовать в новом наблюдении", type="primary", key=f"draft_accept_{scope}"):
        st.session_state[NEW_SECTION_KEY] = sec
        st.session_state[NEW_OBS_KEY] = draft
        del st.session_state[DRAFT_RESULT_KEY]
        st.rerun()
    if b.button("❌ Отклонить", key=f"draft_reject_{scope}"):
        del st.session_state[DRAFT_RESULT_KEY]
        st.rerun()


# ---------------------------------------------------------------------------
# Add new finding (plain widgets, not a form — so AI buttons can sit inline)
# ---------------------------------------------------------------------------
st.subheader("Добавить наблюдение")

c1, c2 = st.columns([1, 3])
with c1:
    new_section = st.selectbox(
        "Раздел",
        options=SECTION_KEYS,
        format_func=lambda x: SECTION_LABELS[x],
        key=NEW_SECTION_KEY,
        help="**Разделы 11 и 14 — только аудитор, без ИИ-помощи.**",
    )
    new_severity = st.selectbox(
        "Серьёзность",
        options=SEVERITY_OPTIONS,
        format_func=lambda s: SEVERITY_LABELS[s],
        key=NEW_SEV_KEY,
        help=SEVERITY_HELP,
    )
with c2:
    new_observation = st.text_area(
        "Наблюдение (тезисами или прозой; на эстонском)",
        height=100,
        key=NEW_OBS_KEY,
        help=(
            "Что вы увидели на объекте. На эстонском — отчёт идёт в "
            "Ehitisregister на эстонском. Для черновика тезисов используйте "
            "ИИ-помощник выше."
        ),
    )
    new_recommendation = st.text_area(
        "Рекомендация (опционально)",
        height=60,
        key=f"new_finding_rec_{scope}",
        help="Что владельцу следует сделать.",
    )
    improve_button_for(
        text=new_recommendation or "",
        state_key_prefix=f"imp_new_rec_{scope}",
        section_ref=new_section,
        text_widget_key=f"new_finding_rec_{scope}",
        apply=lambda _v: None,  # widget value is restored via flush_improve_pending
    )

suggestions = _legal_refs_for(new_section)
new_legal_codes: list[str] = []
if suggestions:
    new_legal_codes = st.multiselect(
        "Ссылки на закон (предложения для этого раздела)",
        options=[r.code for r in suggestions],
        format_func=lambda c: f"{c} — {next(r.title_et for r in suggestions if r.code == c)[:60]}",
        key=f"new_finding_refs_{scope}",
        help=(
            "Какие нормы нарушены или подтверждены этим наблюдением. "
            "Список — из курируемой таблицы legal/references.yaml. "
            "ИИ может ранжировать варианты, но никогда не придумывает новые."
        ),
    )

add_col, _ = st.columns([1, 4])
if add_col.button("➕ Добавить наблюдение", type="primary", key=f"add_finding_{scope}"):
    if not new_observation.strip():
        st.error("Наблюдение не может быть пустым.")
    else:
        audit.findings.append(
            Finding(
                section_ref=new_section,
                severity=new_severity,
                observation_raw=new_observation.strip(),
                recommendation=new_recommendation.strip() or None,
                legal_ref_codes=new_legal_codes,
            )
        )
        # Remember last-used section/severity for the next new-finding form.
        st.session_state[_LAST_SECTION_KEY] = new_section
        st.session_state[_LAST_SEVERITY_KEY] = new_severity
        # Clear new-finding state so the form is empty for the next entry.
        st.session_state[NEW_OBS_KEY] = ""
        st.session_state[f"new_finding_rec_{scope}"] = ""
        set_current(audit)
        st.success("Наблюдение добавлено")
        st.rerun()


# ---------------------------------------------------------------------------
# Edit / delete existing findings, with per-finding AI helpers
# ---------------------------------------------------------------------------
st.subheader(f"Все наблюдения ({len(audit.findings)})")
if not audit.findings:
    st.caption(
        "Пока нет наблюдений. Добавьте хотя бы одну в каждый из обязательных "
        "разделов: 11 (Kokkuvõte) и 14 (Lõpphinnang)."
    )
else:
    # ---- At-a-glance completeness table ----
    # Lets the auditor see which findings still need a recommendation or
    # legal-ref without expanding every panel.
    has_11 = any(ff.section_ref.startswith("11") for ff in audit.findings)
    has_14 = any(ff.section_ref.startswith("14") for ff in audit.findings)
    if not (has_11 and has_14):
        miss = []
        if not has_11:
            miss.append("11 (Kokkuvõte)")
        if not has_14:
            miss.append("14 (Lõpphinnang)")
        st.warning(f"⚠️ Не хватает наблюдений в разделах: {', '.join(miss)}")

    rows = []
    for idx, ff in enumerate(audit.findings):
        is_locked_section = ff.section_ref.split(".")[0] in {"11", "14"}
        # legal_ref is only required for non-info severity AND for non-auditor-only
        # sections; sections 11/14 don't need formal refs in the body.
        needs_ref = ff.severity != "info" and not is_locked_section
        has_ref = bool(ff.legal_ref_codes)
        has_rec = bool((ff.recommendation or "").strip())
        rows.append({
            "#": idx + 1,
            "Раздел": ff.section_ref,
            "Тяжесть": SEVERITY_LABELS.get(ff.severity, ff.severity),
            "Закон": "✅" if has_ref else ("⚠️" if needs_ref else "—"),
            "Рек.": "✅" if has_rec else "—",
            "Текст": (ff.observation_raw or "")[:60] + ("…" if len(ff.observation_raw or "") > 60 else ""),
        })
    st.dataframe(rows, hide_index=True, use_container_width=True)

if "_pending_delete" not in st.session_state:
    st.session_state._pending_delete = None


def _polish_key(i: int) -> str:
    return f"_polish_result_{scope}_{i}"


def _rank_key(i: int) -> str:
    return f"_rank_result_{scope}_{i}"


for i, f in enumerate(audit.findings):
    # Title: section ref + section name only — e.g. "7.1. Veevarustus".
    title = SECTION_LABELS.get(f.section_ref, f.section_ref)
    expanded = st.session_state._pending_delete == i

    # If a previous click on "Добавить к наблюдению" stashed merged refs,
    # apply them BEFORE the multiselect renders in this run (Streamlit forbids
    # writing the widget's session_state key after the widget exists). We pop
    # the widget key too so it reseeds from default=f.legal_ref_codes.
    _pending_refs_key = f"_pending_refs_{scope}_{i}"
    if _pending_refs_key in st.session_state:
        f.legal_ref_codes = st.session_state.pop(_pending_refs_key)
        st.session_state.pop(f"refs_{scope}_{i}", None)
        set_current(audit)

    with st.expander(title, expanded=expanded):
        # ---- Inline edit (plain widgets — not a form so all action buttons
        # can sit in one row including Save). ----
        ec1, ec2 = st.columns([1, 3])
        with ec1:
            edited_section = st.selectbox(
                "Раздел",
                options=SECTION_KEYS,
                index=SECTION_KEYS.index(f.section_ref) if f.section_ref in SECTION_KEYS else 0,
                format_func=lambda x: SECTION_LABELS[x],
                key=f"sec_{scope}_{i}",
            )
            edited_severity = st.selectbox(
                "Серьёзность",
                options=SEVERITY_OPTIONS,
                index=SEVERITY_OPTIONS.index(f.severity),
                format_func=lambda s: SEVERITY_LABELS[s],
                key=f"sev_{scope}_{i}",
            )
        with ec2:
            edited_observation = st.text_area(
                "Наблюдение",
                value=f.observation_raw,
                height=100,
                key=f"obs_{scope}_{i}",
            )
            edited_recommendation = st.text_area(
                "Рекомендация",
                value=f.recommendation or "",
                height=60,
                key=f"rec_{scope}_{i}",
            )
            improve_button_for(
                text=edited_recommendation or "",
                state_key_prefix=f"imp_rec_{scope}_{i}",
                section_ref=f.section_ref,
                text_widget_key=f"rec_{scope}_{i}",
                apply=lambda v, _f=f: setattr(_f, "recommendation", v or None),
            )

        section_for_refs = edited_section if edited_section else f.section_ref
        sugs = _legal_refs_for(section_for_refs)
        available_codes = sorted({r.code for r in sugs} | set(f.legal_ref_codes))

        def _ref_label(c: str, _sugs=sugs) -> str:
            title_match = next((r.title_et for r in _sugs if r.code == c), "")
            return f"{c} — {title_match[:60]}" if title_match else c

        edited_legal_codes = st.multiselect(
            "Ссылки на закон",
            options=available_codes,
            default=f.legal_ref_codes,
            format_func=_ref_label,
            key=f"refs_{scope}_{i}",
        )

        # ---- Auto-persist edits to the in-memory Finding on every rerun.
        # This prevents the auditor from losing typed-but-unsaved text when
        # they navigate to another page; the explicit «💾 Сохранить» button
        # below now acts as a checkpoint/confirmation rather than the only
        # gate to memory. (DB write still requires «Сохранить черновик» on
        # the «Готовый отчёт» page.)
        if edited_observation.strip():
            f.observation_raw = edited_observation.strip()
        f.recommendation = edited_recommendation.strip() or None
        f.section_ref = edited_section
        f.severity = edited_severity
        f.legal_ref_codes = edited_legal_codes

        # ---- Action row: Save + AI buttons + Delete, all on ONE line ----
        polish_disabled = is_locked(f.section_ref)
        in_delete = st.session_state._pending_delete == i

        if in_delete:
            dc1, dc2, _ = st.columns([1, 1, 3])
            if dc1.button(
                "✅ Подтвердить удаление", key=f"confirm_del_{scope}_{i}", type="primary"
            ):
                audit.findings.pop(i)
                st.session_state._pending_delete = None
                set_current(audit)
                st.rerun()
            if dc2.button("Отмена", key=f"cancel_del_{scope}_{i}"):
                st.session_state._pending_delete = None
                st.rerun()
        else:
            b1, b2, b3, b4 = st.columns(4)
            save_clicked = b1.button(
                "💾 Сохранить",
                key=f"save_{scope}_{i}",
                type="primary",
                use_container_width=True,
            )
            # Polish/Rank buttons render always — disabled when LLM is off so
            # the auditor sees the integrations exist (vs. silently missing).
            if polish_disabled:
                polish_help = "Раздел 11/14 — только аудитор."
            elif not llm_on:
                polish_help = "ИИ выключен — настройте ANTHROPIC_API_KEY."
            else:
                polish_help = "Sonnet поправит грамматику и терминологию, не меняя факты."
            rank_help = (
                "Haiku ранжирует подходящие ссылки из курируемого списка."
                if llm_on
                else "ИИ выключен — настройте ANTHROPIC_API_KEY."
            )
            polish_clicked = b2.button(
                "✏️ Polish",
                key=f"polish_btn_{scope}_{i}",
                disabled=polish_disabled or not llm_on,
                help=polish_help,
                use_container_width=True,
            )
            rank_clicked = b3.button(
                "💡 Ссылки",
                key=f"rank_btn_{scope}_{i}",
                disabled=not llm_on,
                help=rank_help,
                use_container_width=True,
            )
            del_clicked = b4.button(
                "🗑️ Удалить",
                key=f"del_{scope}_{i}",
                use_container_width=True,
            )

            if save_clicked:
                if not edited_observation.strip():
                    st.error("Наблюдение не может быть пустым.")
                else:
                    # Auto-persist already wrote the edits above; this button
                    # remains as an explicit checkpoint that flushes the
                    # in-memory model and confirms to the auditor.
                    set_current(audit)
                    st.success("Изменения зафиксированы")
                    st.rerun()

            if del_clicked:
                st.session_state._pending_delete = i
                st.rerun()

            if polish_clicked:
                with st.status("Sonnet 4.6 правит грамматику…", expanded=True) as status:
                    try:
                        polished = polish_text(
                            f.observation_raw, section_ref=f.section_ref
                        )
                        st.session_state[_polish_key(i)] = polished
                        _clear_error()
                        status.update(label="Готово ✅", state="complete", expanded=False)
                    except Exception as e:
                        _record_error(f"Polish (наблюдение #{i + 1}) не удался", e)
                        status.update(label="Ошибка ❌", state="error", expanded=True)
                st.rerun()

            if rank_clicked:
                with st.status(
                    "Haiku 4.5 ранжирует ссылки на закон…", expanded=True
                ) as status:
                    try:
                        ranked = rank_legal_refs(
                            f.observation_raw,
                            audit_type=audit.type,
                            section_ref=f.section_ref,
                        )
                        st.session_state[_rank_key(i)] = ranked
                        _clear_error()
                        status.update(label="Готово ✅", state="complete", expanded=False)
                    except Exception as e:
                        _record_error(
                            f"Подбор ссылок (наблюдение #{i + 1}) не удался", e
                        )
                        status.update(label="Ошибка ❌", state="error", expanded=True)
                st.rerun()

        # ---- Polish result panel ----
        if llm_on and _polish_key(i) in st.session_state:
            polished = st.session_state[_polish_key(i)]
            if polished == f.observation_raw:
                st.info("✅ Polish: правок не требуется — текст уже чистый.")
                if st.button("OK", key=f"polish_ok_{scope}_{i}"):
                    del st.session_state[_polish_key(i)]
                    st.rerun()
            else:
                st.markdown("**Polish-предложение:**")
                pc1, pc2 = st.columns(2)
                with pc1:
                    st.caption("Было:")
                    st.markdown(f"> {f.observation_raw}")
                with pc2:
                    st.caption("Стало:")
                    st.markdown(f"> {polished}")
                pa, pb = st.columns(2)
                if pa.button("✅ Принять polish", key=f"polish_accept_{scope}_{i}"):
                    f.observation_raw = polished
                    # Same widget-state rule as the ranker — pop the text_area's
                    # session_state key so it reseeds from value=f.observation_raw
                    # on the next run instead of setting it (which Streamlit
                    # forbids after the widget has rendered).
                    st.session_state.pop(f"obs_{scope}_{i}", None)
                    del st.session_state[_polish_key(i)]
                    set_current(audit)
                    st.rerun()
                if pb.button("❌ Отклонить polish", key=f"polish_reject_{scope}_{i}"):
                    del st.session_state[_polish_key(i)]
                    st.rerun()

        # ---- Ranker result panel ----
        if llm_on and _rank_key(i) in st.session_state:
            ranked = st.session_state[_rank_key(i)]
            if not ranked:
                st.info("Не нашёл подходящих ссылок для этого раздела.")
                if st.button("OK", key=f"rank_ok_{scope}_{i}"):
                    del st.session_state[_rank_key(i)]
                    st.rerun()
            else:
                st.markdown("**Предложения ИИ:**")
                for code in ranked:
                    st.write(f"• `{code}`")
                ra, rb = st.columns(2)
                if ra.button(
                    "✅ Добавить к наблюдению",
                    key=f"rank_accept_{scope}_{i}",
                    type="primary",
                ):
                    # Streamlit forbids writing the multiselect's widget-state
                    # key (refs_…) after the widget has rendered this run. We
                    # stash the merged list in a non-widget slot; the top of
                    # the loop iteration applies it before the next render.
                    current = st.session_state.get(
                        f"refs_{scope}_{i}", f.legal_ref_codes
                    )
                    merged = list(dict.fromkeys([*current, *ranked]))
                    st.session_state[f"_pending_refs_{scope}_{i}"] = merged
                    del st.session_state[_rank_key(i)]
                    st.rerun()
                if rb.button("❌ Отклонить", key=f"rank_reject_{scope}_{i}"):
                    del st.session_state[_rank_key(i)]
                    st.rerun()
