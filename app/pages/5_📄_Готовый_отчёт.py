from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from pathlib import Path  # noqa: E402

import streamlit as st  # noqa: E402

from app._state import get_current  # noqa: E402
from tadf.config import AUDITS_DIR  # noqa: E402
from tadf.db.repo import upsert_audit  # noqa: E402
from tadf.db.session import session_scope  # noqa: E402
from tadf.legal.checklist import check, soft_warnings  # noqa: E402
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
