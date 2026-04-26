"""Home page content. Loaded by app/main.py via st.navigation as the
default page. Layout, auth, and sidebar are owned by main.py — this file
only renders the welcome content.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from app._state import all_saved_audits
from tadf import __version__

# Logo header
_LOGO = Path(__file__).resolve().parent.parent / "assets" / "logo.svg"
if _LOGO.exists():
    cols = st.columns([1, 3, 1])
    with cols[1]:
        st.image(str(_LOGO), width=320)

st.title("TADF — Помощник аудитора")
st.caption(f"v{__version__}")
st.markdown(
    """
Добро пожаловать в инструмент для составления отчётов *ehitise auditi aruanne*.

Используйте боковое меню для перехода по этапам:

1. **📝 Новый аудит** — создать или открыть аудит, заполнить метаданные.
2. **🏠 Здание** — данные объекта (адрес, кадастр, EHR-код, размеры, год постройки).
3. **🔍 Находки** — структурированные находки с рекомендациями и ссылками на закон.
4. **📸 Фото** — фотографии с подписями (ИИ-помощник для подписей).
5. **📄 Готовый отчёт** — проверка по §5 + сборка `.docx`.
6. **📚 Правовая база** — справочник всех правовых ссылок, доступных ИИ-ранжировщику.

Файлы каждого аудита сохраняются в `data/audits/<id>/` (включая `context.json`
для воспроизведения и обязательного 7-летнего хранения).
"""
)

# Quick stats
saved = all_saved_audits()
if saved:
    cols = st.columns(3)
    cols[0].metric("Сохранённых аудитов", len(saved))
    total_findings = sum(len(a.findings) for a in saved)
    cols[1].metric("Всего находок", total_findings)
    total_photos = sum(len(a.photos) for a in saved)
    cols[2].metric("Всего фото", total_photos)
else:
    st.info("Пока нет сохранённых аудитов. Откройте «📝 Новый аудит», чтобы начать.")

# Cloud-environment warning. Streamlit Community Cloud sets HOSTNAME to
# something starting with 'streamlit' on its workers.
if os.environ.get("STREAMLIT_SHARING_MODE") or "streamlit" in os.environ.get("HOSTNAME", "").lower():
    st.warning(
        "⚠️ **Демо-режим (Streamlit Cloud)** — файловая система этого хостинга "
        "временная. База данных и загруженные фото пропадают при каждом перезапуске. "
        "Для реальной работы используйте локальную установку или Hetzner-деплой."
    )
