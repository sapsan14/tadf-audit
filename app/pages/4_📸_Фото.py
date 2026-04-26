from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / 'src'))

import hashlib
from pathlib import Path

import streamlit as st

from app._state import get_current, set_current
from tadf.config import AUDITS_DIR
from tadf.models import Photo

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
    SECTION_REFS = ["4", "5", "6", "6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "7", "8", "16"]
    default_section = st.selectbox(
        "Раздел отчёта (по умолчанию для всех загруженных)", SECTION_REFS, index=0
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
cols = st.columns(3)
for i, p in enumerate(audit.photos):
    with cols[i % 3]:
        path = Path(p.path)
        if path.exists():
            st.image(
                str(path), caption=f"[{p.section_ref}] {p.caption_auditor or ''}", width="stretch"
            )
        new_caption = st.text_input(
            f"Подпись #{i + 1}", value=p.caption_auditor or "", key=f"cap_{i}"
        )
        new_section = st.text_input(f"Раздел #{i + 1}", value=p.section_ref or "16", key=f"sec_{i}")
        p.caption_auditor = new_caption
        p.section_ref = new_section
        if st.button("Удалить", key=f"delphoto_{i}"):
            audit.photos.pop(i)
            set_current(audit)
            st.rerun()
