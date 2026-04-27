from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import hashlib  # noqa: E402
from pathlib import Path  # noqa: E402

import streamlit as st  # noqa: E402

from app._state import get_current, set_current  # noqa: E402
from app._widgets import flush_improve_pending, improve_button_for  # noqa: E402
from tadf.config import AUDITS_DIR  # noqa: E402
from tadf.llm import caption_photo  # noqa: E402
from tadf.llm import is_available as llm_available  # noqa: E402
from tadf.models import Photo  # noqa: E402
from tadf.sections import SECTION_KEYS as ALL_SECTION_KEYS  # noqa: E402
from tadf.sections import SECTION_LABELS as ALL_SECTION_LABELS  # noqa: E402

flush_improve_pending()

st.title("Фотографии")

audit = get_current()
audit_id = audit.id or "draft"
photos_dir = Path(AUDITS_DIR) / str(audit_id) / "photos"
photos_dir.mkdir(parents=True, exist_ok=True)

st.caption(
    f"Папка: `{photos_dir.relative_to(Path.cwd()) if photos_dir.is_relative_to(Path.cwd()) else photos_dir}`"
)

uploaded = st.file_uploader(
    "Загрузить фото (можно несколько)",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True,
)

if uploaded:
    default_section = st.selectbox(
        "Раздел отчёта (по умолчанию для всех загруженных)",
        options=ALL_SECTION_KEYS,
        format_func=lambda k: ALL_SECTION_LABELS[k],
        index=ALL_SECTION_KEYS.index("16") if "16" in ALL_SECTION_KEYS else 0,
    )
    if st.button(f"Сохранить {len(uploaded)} фото", type="primary"):
        for f in uploaded:
            data = f.read()
            sha = hashlib.sha256(data).hexdigest()[:16]
            ext = Path(f.name).suffix
            target = photos_dir / f"{sha}{ext}"
            target.write_bytes(data)
            audit.photos.append(
                Photo(
                    path=str(target),
                    sha256=sha,
                    section_ref=default_section,
                    caption_auditor=f.name,
                )
            )
        set_current(audit)
        st.success(f"Сохранено {len(uploaded)} фото")
        st.rerun()

st.subheader(f"Загруженные фото ({len(audit.photos)})")

llm_on = llm_available()
if not llm_on:
    st.caption(
        "💡 ИИ-помощник для подписей сейчас выключен (нет ключа Anthropic). "
        "Подписи и разделы можно проставить вручную."
    )

# Persistent error slot — same pattern as page 3
PHOTO_ERROR_KEY = "_photo_ai_error"
if PHOTO_ERROR_KEY in st.session_state:
    with st.container(border=True):
        st.error(f"🤖❌ Ошибка ИИ: {st.session_state[PHOTO_ERROR_KEY]}")
        if st.button("Закрыть", key="close_photo_err"):
            del st.session_state[PHOTO_ERROR_KEY]
            st.rerun()

cols = st.columns(3)
for i, p in enumerate(audit.photos):
    with cols[i % 3]:
        path = Path(p.path)
        if path.exists():
            st.image(
                str(path),
                caption=f"[{p.section_ref}] {p.caption_auditor or ''}",
                width="stretch",
            )

        new_caption = st.text_input(
            f"Подпись #{i + 1}", value=p.caption_auditor or "", key=f"cap_{i}"
        )
        new_section = st.text_input(
            f"Раздел #{i + 1}", value=p.section_ref or "16", key=f"sec_{i}"
        )
        p.caption_auditor = new_caption
        p.section_ref = new_section

        ai_col, del_col = st.columns(2)
        with ai_col:
            ai_clicked = st.button(
                "🤖 ИИ-подпись",
                key=f"ai_caption_{i}",
                disabled=not llm_on,
                help=(
                    "Claude Haiku посмотрит фото и предложит эстонскую подпись + "
                    "номер раздела. Текущие значения перезапишутся — можно редактировать."
                ),
            )
            if ai_clicked and path.exists():
                with st.status(
                    f"Haiku 4.5 смотрит фото #{i + 1}…", expanded=True
                ) as status:
                    st.write(f"Файл: {path.name}")
                    try:
                        result = caption_photo(path, auditor_note=new_caption)
                        p.caption_auditor = result["caption"]
                        p.section_ref = result["section_ref"]
                        # CRITICAL: also push into the widget's session_state so
                        # the text_input on the next render shows the new value
                        # (Streamlit ignores `value=` once the key exists).
                        st.session_state[f"cap_{i}"] = result["caption"]
                        st.session_state[f"sec_{i}"] = result["section_ref"]
                        st.session_state.pop(PHOTO_ERROR_KEY, None)
                        status.update(label="Готово ✅", state="complete", expanded=False)
                        set_current(audit)
                    except Exception as e:
                        st.session_state[PHOTO_ERROR_KEY] = (
                            f"Подпись фото #{i + 1}: {type(e).__name__}: {e}"
                        )
                        status.update(label="Ошибка ❌", state="error", expanded=True)
                st.rerun()
        with del_col:
            if st.button("🗑️", key=f"delphoto_{i}"):
                audit.photos.pop(i)
                set_current(audit)
                st.rerun()

        # Polish/translate for the manual caption — useful when the auditor
        # types short Russian notes or rough Estonian and wants the text in
        # formal Estonian without using the vision-based AI caption.
        improve_button_for(
            text=new_caption or "",
            state_key_prefix=f"imp_cap_{i}",
            section_ref=p.section_ref,
            text_widget_key=f"cap_{i}",
            apply=lambda v, _p=p: setattr(_p, "caption_auditor", v),
            label="✨ Улучшить подпись",
        )
