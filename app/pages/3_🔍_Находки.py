from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import streamlit as st  # noqa: E402

from app._state import get_current, set_current  # noqa: E402
from tadf.legal.loader import for_section  # noqa: E402
from tadf.models import Finding  # noqa: E402
from tadf.sections import SECTION_KEYS, SECTION_LABELS  # noqa: E402

st.title("Находки и наблюдения")
st.caption(
    "Выбор раздела опирается на структуру 14-секционного отчёта (Tiitelleht → "
    "Allkirjad). Подразделы (6.1–6.15, 7.1–7.10, 8.1–8.13 и т.д.) добавлены "
    "из стандартов EVS 812-7 / EVS 932 и из ваших старых отчётов."
)

audit = get_current()
scope = audit.id or "new"

SEVERITY_OPTIONS = ["info", "nonconf_minor", "nonconf_major", "hazard"]
SEVERITY_LABELS = {
    "info": "📝 Инфо",
    "nonconf_minor": "⚠️ Мелкое несоответствие",
    "nonconf_major": "❗ Существенное несоответствие",
    "hazard": "🛑 Опасность",
}


def _legal_refs_for(section_ref: str) -> list:
    return for_section(section_ref.split(".")[0], audit.type)


# ---------------------------------------------------------------------------
# Add new finding
# ---------------------------------------------------------------------------
SEVERITY_HELP = (
    "📝 Инфо — нейтральное наблюдение, нет нарушений\n"
    "⚠️ Мелкое несоответствие — отклонение от нормы, не угрожает безопасности\n"
    "❗ Существенное несоответствие — нарушение требований Ehitusseadustik / EVS, "
    "требуется устранение\n"
    "🛑 Опасность — непосредственная угроза жизни/здоровью, требуется немедленное "
    "действие (упоминается в Lõpphinnang)"
)

st.subheader("Добавить находку")
with st.form(f"new_finding_{scope}", clear_on_submit=True):
    col1, col2 = st.columns([1, 3])
    with col1:
        new_section = st.selectbox(
            "Раздел",
            options=SECTION_KEYS,
            format_func=lambda x: SECTION_LABELS[x],
            help=(
                "Раздел отчёта, к которому относится находка. Подразделы (6.1, "
                "8.8 и т.д.) добавлены из EVS 812-7 / EVS 932 + ваших старых "
                "отчётов. **Разделы 11 и 14 — только аудитор, без ИИ-помощи.**"
            ),
        )
        new_severity = st.selectbox(
            "Серьёзность",
            options=SEVERITY_OPTIONS,
            format_func=lambda s: SEVERITY_LABELS[s],
            help=SEVERITY_HELP,
        )
    with col2:
        new_observation = st.text_area(
            "Наблюдение (тезисами или прозой; на эстонском)",
            height=100,
            help=(
                "Что вы увидели на объекте. На эстонском, потому что отчёт "
                "идёт в Ehitisregister на эстонском. Можно тезисами — на "
                "фазе 2 ИИ поможет развернуть в формальную прозу с вашим "
                "одобрением каждой строки."
            ),
        )
        new_recommendation = st.text_area(
            "Рекомендация (опционально)",
            height=60,
            help=(
                "Что владельцу следует сделать. Например «Заменить катусекатте "
                "в течение 6 месяцев». Помогает заказчику и попадает в "
                "Lõpphinnang."
            ),
        )

    suggestions = _legal_refs_for(new_section)
    new_legal_codes: list[str] = []
    if suggestions:
        new_legal_codes = st.multiselect(
            "Ссылки на закон (предложения для этого раздела)",
            options=[r.code for r in suggestions],
            format_func=lambda c: f"{c} — {next(r.title_et for r in suggestions if r.code == c)[:60]}",
            help=(
                "Какие нормы нарушены или подтверждены этой находкой. "
                "Список — из курируемой таблицы legal/references.yaml. "
                "На фазе 2 ИИ предложит ранжированные варианты, но никогда "
                "не придумает новые ссылки."
            ),
        )

    if st.form_submit_button("➕ Добавить находку", type="primary") and new_observation.strip():
        audit.findings.append(
            Finding(
                section_ref=new_section,
                severity=new_severity,
                observation_raw=new_observation.strip(),
                recommendation=new_recommendation.strip() or None,
                legal_ref_codes=new_legal_codes,
            )
        )
        set_current(audit)
        st.success("Находка добавлена")
        st.rerun()


# ---------------------------------------------------------------------------
# Edit / delete existing findings
# ---------------------------------------------------------------------------
st.subheader(f"Все находки ({len(audit.findings)})")
if not audit.findings:
    st.caption(
        "Пока нет находок. Добавьте хотя бы одну в каждый из обязательных "
        "разделов: 11 (Kokkuvõte) и 14 (Lõpphinnang)."
    )

# Track which finding is in delete-confirm mode
if "_pending_delete" not in st.session_state:
    st.session_state._pending_delete = None

for i, f in enumerate(audit.findings):
    severity_icon = SEVERITY_LABELS[f.severity].split(" ", 1)[0]
    # Collapse newlines and whitespace so the expander header is always a single
    # readable line, not the start of a wrapped paragraph.
    preview = " ".join(f.observation_raw.split())[:80] or "(пусто)"
    section_label = SECTION_LABELS.get(f.section_ref, f.section_ref).split(".", 1)[0]
    title = f"{i + 1}. {severity_icon} [{section_label}] {preview}"
    expanded = st.session_state._pending_delete == i
    with st.expander(title, expanded=expanded):
        # ---- Inline edit form ----
        with st.form(f"edit_finding_{scope}_{i}"):
            col1, col2 = st.columns([1, 3])
            with col1:
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
            with col2:
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

            # Legal refs — show suggestions for the *current* section, but also
            # preserve any refs already attached even if they're outside the suggestion list.
            section_for_refs = edited_section if edited_section else f.section_ref
            suggestions = _legal_refs_for(section_for_refs)
            available_codes = sorted({r.code for r in suggestions} | set(f.legal_ref_codes))

            def _ref_label(c: str, _sugs=suggestions) -> str:
                title_match = next((r.title_et for r in _sugs if r.code == c), "")
                return f"{c} — {title_match[:60]}" if title_match else c

            edited_legal_codes = st.multiselect(
                "Ссылки на закон",
                options=available_codes,
                default=f.legal_ref_codes,
                format_func=_ref_label,
                key=f"refs_{scope}_{i}",
            )

            saved = st.form_submit_button("💾 Сохранить", type="primary")
            if saved:
                if not edited_observation.strip():
                    st.error("Наблюдение не может быть пустым.")
                else:
                    f.section_ref = edited_section
                    f.severity = edited_severity
                    f.observation_raw = edited_observation.strip()
                    f.recommendation = edited_recommendation.strip() or None
                    f.legal_ref_codes = edited_legal_codes
                    set_current(audit)
                    st.success("Изменения сохранены")
                    st.rerun()

        # ---- Delete (outside form, with confirm) ----
        st.divider()
        if st.session_state._pending_delete == i:
            cdel1, cdel2 = st.columns(2)
            with cdel1:
                if st.button("✅ Подтвердить удаление", key=f"confirm_del_{scope}_{i}", type="primary"):
                    audit.findings.pop(i)
                    st.session_state._pending_delete = None
                    set_current(audit)
                    st.rerun()
            with cdel2:
                if st.button("Отмена", key=f"cancel_del_{scope}_{i}"):
                    st.session_state._pending_delete = None
                    st.rerun()
        else:
            if st.button("🗑️ Удалить находку", key=f"del_{scope}_{i}"):
                st.session_state._pending_delete = i
                st.rerun()
