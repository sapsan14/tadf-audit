"""TADF audit-report builder — Streamlit entry point.

UI language: Russian (Fjodor's native language) with Estonian terms preserved
for fields that appear in the report itself.

Run from project root:
    uv run streamlit run app/main.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure `src/` is on sys.path so `from tadf...` works even when the package
# is not pip-installed (e.g. Streamlit Community Cloud builds).
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

import streamlit as st  # noqa: E402

from tadf.config import ROOT  # noqa: E402
from tadf.corpus.preload import preload_corpus  # noqa: E402
from tadf.db.session import init_db  # noqa: E402

st.set_page_config(
    page_title="TADF — Аудит",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()


@st.cache_resource
def _preload_corpus_once() -> tuple[int, int]:
    """Idempotent preload of historical reports under /audit/.

    Cached at process scope so it runs once per Streamlit worker. Skips entirely
    on Streamlit Cloud (no /audit/ folder there) — only runs on local installs
    where Fjodor has the original audit folder.
    """
    audit_dir = ROOT / "audit"
    if not audit_dir.exists():
        return (0, 0)
    return preload_corpus(audit_dir)


_imported, _skipped = _preload_corpus_once()

st.title("TADF — Помощник аудитора")
st.markdown(
    """
Добро пожаловать в инструмент для составления отчётов *ehitise auditi aruanne*.

Используйте боковое меню для перехода по этапам:

1. **Новый аудит** — создать или открыть аудит, заполнить метаданные.
2. **Здание** — данные объекта (адрес, кадастр, EHR-код, размеры, год постройки).
3. **Наблюдения** — фото и тезисные заметки по разделам отчёта.
4. **Находки** — структурированные находки с рекомендациями и ссылками на закон.
5. **Готовый отчёт** — проверка по §5 + сборка `.docx`.

Файлы каждого аудита сохраняются в `data/audits/<id>/` (включая `context.json`
для воспроизведения и обязательного 7-летнего хранения).
"""
)

st.info(
    "MVP-фаза: ИИ-помощь и подписание ASiC-E подключаются на следующих этапах. "
    "Сейчас программа полностью локальная, без обращения к внешним сервисам."
)

if _imported:
    st.success(
        f"📥 Предзагружено {_imported} исторических отчётов из папки `audit/` "
        f"в базу. Откройте «Новый аудит» → «Открыть сохранённый аудит» для просмотра."
    )

# Cloud-environment warning. Streamlit Community Cloud sets HOSTNAME to
# something starting with 'streamlit' on its workers.
if os.environ.get("STREAMLIT_SHARING_MODE") or "streamlit" in os.environ.get("HOSTNAME", "").lower():
    st.warning(
        "⚠️ **Демо-режим (Streamlit Cloud)** — файловая система этого "
        "хостинга временная. База данных и загруженные фото пропадают при "
        "каждом перезапуске приложения. Для реальной работы используйте "
        "локальную установку (см. README) или подождите фазу 5 (Hetzner)."
    )
