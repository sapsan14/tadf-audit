"""Home page content. Loaded by app/main.py via st.navigation as the
default page. Layout, auth, and sidebar (including logo + version) are
owned by main.py + _style.py — this file only renders the welcome content.
"""

from __future__ import annotations

import os

import streamlit as st

from app._state import all_saved_audits
from tadf.external.prewarm import warm_all_async


@st.cache_resource
def _start_prewarm():
    """Refresh Ariregister + In-ADS caches in the background once per
    python process. Daemon thread — never blocks UI, never holds up
    Streamlit shutdown. Errors are swallowed inside the worker so a
    flaky network at startup just means the cache stays whatever it
    already was."""
    return warm_all_async()


_start_prewarm()

st.title("TADF — Помощник аудитора")
st.markdown(
    """
Добро пожаловать в инструмент для составления отчётов *ehitise auditi aruanne*.

Используйте боковое меню для перехода по этапам:

1. **📝 Новый аудит** — создать или открыть аудит, заполнить метаданные.
2. **🏠 Здание** — данные объекта (адрес, кадастр, EHR-код, размеры, год постройки).
3. **🔍 Наблюдения** — структурированные наблюдения с рекомендациями и ссылками на закон.
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
    cols[1].metric("Всего наблюдений", total_findings)
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
