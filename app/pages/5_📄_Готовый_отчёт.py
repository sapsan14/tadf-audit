from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from app._style import apply_consistent_layout  # noqa: E402

apply_consistent_layout()

from app._auth import require_login  # noqa: E402

require_login()  # gate every page individually

from pathlib import Path  # noqa: E402

import streamlit as st  # noqa: E402

from app._state import get_current  # noqa: E402
from tadf.config import AUDITS_DIR  # noqa: E402
from tadf.db.repo import save_audit  # noqa: E402
from tadf.db.session import session_scope  # noqa: E402
from tadf.legal.checklist import check  # noqa: E402
from tadf.render.docx_render import ChecklistFailed, render_to_path  # noqa: E402

st.title("Готовый отчёт")

audit = get_current()

st.header("Проверка по §5 (Ehitise auditi tegemise kord)")
missing = check(audit)
if not missing:
    st.success("✅ Все обязательные поля заполнены — отчёт готов к рендеру.")
else:
    st.error(f"❌ Не заполнено {len(missing)} обязательных пункт(ов):")
    for m in missing:
        with st.container(border=True):
            st.markdown(f"**`{m.field}`** → форма «{m.section_hint}»  \n🇪🇪 {m.why_et}  \n🇷🇺 {m.why_ru}")

st.header("Сохранить и собрать .docx")

col1, col2 = st.columns(2)
with col1:
    if st.button("💾 Сохранить аудит в БД", type="secondary"):
        with session_scope() as s:
            audit_id = save_audit(s, audit)
        audit.id = audit_id
        st.success(f"Сохранено как audit #{audit_id}")

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
