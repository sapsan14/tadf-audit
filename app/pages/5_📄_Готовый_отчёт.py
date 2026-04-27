from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from pathlib import Path  # noqa: E402

import streamlit as st  # noqa: E402

from app._state import ensure_draft_saved, get_current  # noqa: E402
from tadf.config import AUDITS_DIR  # noqa: E402
from tadf.db.lookups import latest_footer_override, latest_header_override  # noqa: E402
from tadf.db.repo import upsert_audit  # noqa: E402
from tadf.db.session import session_scope  # noqa: E402
from tadf.legal.checklist import check, soft_warnings  # noqa: E402
from tadf.render.context_builder import (  # noqa: E402
    default_footer_text,
    default_header_text,
)
from tadf.render.docx_render import ChecklistFailed, render_to_path  # noqa: E402

st.title("Готовый отчёт")

audit = get_current()

st.header("Проверка по §5 (Ehitise auditi tegemise kord)")
missing = check(audit)
if not missing:
    st.success("✅ Все обязательные поля заполнены — отчёт готов к рендеру.")
else:
    # Map missing-item field → page to jump to. Streamlit needs the path
    # exactly as registered in app/main.py.
    _PAGE_FOR_FIELD = {
        "audit.purpose": "pages/1_📝_Новый_аудит.py",
        "audit.scope": "pages/1_📝_Новый_аудит.py",
        "audit.visit_date": "pages/1_📝_Новый_аудит.py",
        "reviewer.full_name": "pages/1_📝_Новый_аудит.py",
        "reviewer.kutsetunnistus_no": "pages/1_📝_Новый_аудит.py",
        "composer.full_name": "pages/1_📝_Новый_аудит.py",
        "building.address": "pages/2_🏠_Здание.py",
        "building.kataster_no | ehr_code": "pages/2_🏠_Здание.py",
        "building.construction_year": "pages/2_🏠_Здание.py",
        "building.footprint_m2": "pages/2_🏠_Здание.py",
        "findings[section=11]": "pages/3_🔍_Наблюдения.py",
        "findings[section=14]": "pages/3_🔍_Наблюдения.py",
        "findings[section=8]": "pages/3_🔍_Наблюдения.py",
    }
    st.error(f"❌ Не заполнено {len(missing)} обязательных пункт(ов):")
    for idx, m in enumerate(missing):
        with st.container(border=True):
            mc1, mc2 = st.columns([5, 1])
            mc1.markdown(
                f"**`{m.field}`** → форма «{m.section_hint}»  \n"
                f"🇪🇪 {m.why_et}  \n🇷🇺 {m.why_ru}"
            )
            target = _PAGE_FOR_FIELD.get(m.field)
            if target and mc2.button(
                "→ Заполнить",
                key=f"jump_missing_{idx}",
                use_container_width=True,
                help=f"Перейти на «{m.section_hint}» и заполнить.",
            ):
                st.switch_page(target)

# Soft quality warnings — don't block render but flag things that would
# weaken the report at the EHR review (e.g. "major non-conformance" without
# any cited norm).
warnings = soft_warnings(audit)
if warnings:
    with st.container(border=True):
        st.warning(
            f"⚠️ Качество отчёта: {len(warnings)} замечани(е/я). "
            "Не блокирует сборку, но рецензент EHR может задать вопрос."
        )
        for w in warnings:
            st.markdown(f"- **`{w.field}`** — {w.why_ru}")

st.header("Колонтитулы (header / footer)")
st.caption(
    "Текст, который повторяется на каждой странице отчёта. По умолчанию "
    "собирается автоматически из полей аудита (Töö nr, Töö nimetus, "
    "Pädev isik). Если хотите свою формулировку — введите её тут; она "
    "сохранится в этом черновике и будет предложена как стартовое "
    "значение для следующего нового аудита."
)

# Seed values: prefer this draft's existing override; fall back to the
# most-recent override on any OTHER draft; then to the computed default.
_header_seed = (
    audit.header_override
    or (audit.id is None and latest_header_override(exclude_audit_id=None))
    or default_header_text(audit)
)
_footer_seed = (
    audit.footer_override
    or (audit.id is None and latest_footer_override(exclude_audit_id=None))
    or default_footer_text(audit)
)

hc1, hc2 = st.columns(2)
with hc1:
    new_header = st.text_area(
        "Шапка страницы (page header)",
        value=_header_seed,
        height=110,
        help=(
            "Появляется в самом верху каждой страницы. Многострочный текст "
            "поддерживается. Оставьте пустым — программа сгенерирует "
            "значение из Töö nr / Töö nimetus автоматически."
        ),
    )
with hc2:
    new_footer = st.text_area(
        "Подпись внизу страницы (page footer)",
        value=_footer_seed,
        height=110,
        help=(
            "Появляется внизу каждой страницы (под номером страницы). "
            "Обычно: «Pädev isik: ФИО, квалификация, kutsetunnistus N»."
        ),
    )

# Persist to the in-memory model on every rerun. Only treat as «override»
# if the auditor actually deviated from the computed default — that way the
# DB stays NULL for the common case and the renderer auto-recomputes when
# audit fields change.
default_header_now = default_header_text(audit)
default_footer_now = default_footer_text(audit)
audit.header_override = new_header.strip() if new_header.strip() and new_header.strip() != default_header_now.strip() else None
audit.footer_override = new_footer.strip() if new_footer.strip() and new_footer.strip() != default_footer_now.strip() else None

st.header("Сохранить и собрать .docx")

col1, col2 = st.columns(2)
with col1:
    save_label = "💾 Обновить черновик в БД" if audit.id else "💾 Сохранить черновик в БД"
    if st.button(save_label, type="secondary"):
        with session_scope() as s:
            audit_id = upsert_audit(s, audit)
        audit.id = audit_id
        st.session_state["loaded_id"] = audit_id
        st.success(
            f"{'Обновлено' if save_label.startswith('💾 Обновить') else 'Сохранено'} "
            f"как audit #{audit_id}"
        )

with col2:
    enforce = st.checkbox(
        "Применять §5 проверку",
        value=True,
        help="Снимите галочку для предварительного просмотра незавершённого черновика.",
    )
    if st.button("📄 Собрать отчёт (.docx)", type="primary", disabled=bool(missing) and enforce):
        out_dir = Path(AUDITS_DIR) / str(audit.id or "draft")
        try:
            out = render_to_path(audit, out_dir, enforce_checklist=enforce)
            st.success(f"✅ Готово: `{out}`")
            with open(out, "rb") as fh:
                st.download_button(
                    "⬇️ Скачать draft.docx",
                    data=fh.read(),
                    file_name=f"{audit.display_no()}_{audit.type}_{audit.subtype}_draft.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            st.markdown(
                "**Следующие шаги** (вне программы, фаза 1):\n"
                "1. Откройте `draft.docx` в Word/LibreOffice — поправьте формулировки.\n"
                "2. Сохраните и сконвертируйте в PDF (`File → Export to PDF`).\n"
                "3. Подпишите PDF в DigiDoc → получите `.asice`.\n"
                "4. Загрузите `.asice` в [ehitisregister.ee](https://ehitisregister.ee/)."
            )
        except ChecklistFailed as e:
            st.error(str(e))

# Auto-persist any in-memory mutations on this page (e.g. the header/footer
# overrides edited just below) so a browser refresh keeps them.
ensure_draft_saved(audit)
