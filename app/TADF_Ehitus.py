"""TADF audit-report builder — Streamlit entry point.

UI language: Russian (Fjodor's native language) with Estonian terms preserved
for fields that appear in the report itself.

The filename "TADF_Ehitus.py" is what Streamlit shows in the sidebar nav
(underscores → spaces → "TADF Ehitus"). Don't rename without also updating
README + Streamlit Cloud's "Main file path" setting.

Run from project root:
    uv run streamlit run app/TADF_Ehitus.py
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
from tadf.corpus.preload import preload_corpus, preload_demo  # noqa: E402
from tadf.db.session import init_db  # noqa: E402
from tadf.llm import is_available as _llm_available  # noqa: E402
from tadf.llm.usage import summarise as _llm_summary  # noqa: E402

st.set_page_config(
    page_title="TADF — Аудит",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()


@st.cache_resource
def _seed_db_once() -> tuple[int, int, int]:
    """Idempotent DB seeding. Returns (corpus_imports, corpus_skips, demo_inserts).

    On a local install with /audit/ present: preloads parsed historical reports.
    On Streamlit Cloud (no /audit/): inserts hand-crafted demo audits instead.
    Always cached at process scope so it runs once per worker.
    """
    audit_dir = ROOT / "audit"
    if audit_dir.exists():
        imp, skp = preload_corpus(audit_dir)
        return (imp, skp, 0)
    demo_count = preload_demo()
    return (0, 0, demo_count)


_imported, _skipped, _demo_inserted = _seed_db_once()

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
elif _demo_inserted:
    st.success(
        f"🎁 В базу добавлено {_demo_inserted} демо-аудита для ознакомления. "
        f"Откройте «Новый аудит» → «Открыть сохранённый аудит» и попробуйте "
        f"загрузить любой из них."
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


# ---------------------------------------------------------------------------
# Sidebar — Claude API usage tracker (visible on every page)
# ---------------------------------------------------------------------------
def _format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


with st.sidebar:
    if _llm_available():
        s = _llm_summary()
        st.markdown("**🤖 Расход Claude API**")
        if s.calls == 0:
            st.caption("Пока ни одного вызова — расход $0.00")
        else:
            cost_eur = s.cost_usd * 0.92  # rough EUR/USD
            st.markdown(
                f"≈ **\\${s.cost_usd:.4f}** / €{cost_eur:.4f}  ·  "
                f"{s.calls} вызов(ов)  \n"
                f"<small>↑ {_format_tokens(s.input_tokens)} вход · "
                f"↓ {_format_tokens(s.output_tokens)} выход"
                + (
                    f"  ·  кеш ↑{_format_tokens(s.cache_write_tokens)} "
                    f"↓{_format_tokens(s.cache_read_tokens)}"
                    if s.cache_read_tokens or s.cache_write_tokens
                    else ""
                )
                + "</small>",
                unsafe_allow_html=True,
            )
            with st.expander("По моделям", expanded=False):
                for model, m in s.by_model.items():
                    st.markdown(
                        f"**{model}** · {int(m['calls'])} вызов(ов) · "
                        f"\\${m['cost']:.4f}  \n"
                        f"<small>↑ {_format_tokens(int(m['input']))} "
                        f"↓ {_format_tokens(int(m['output']))}</small>",
                        unsafe_allow_html=True,
                    )
        st.caption(
            "Цены оценочные (Sonnet \\$3/\\$15, Haiku \\$1/\\$5 за 1M токенов; "
            "кеш ×0.1/×1.25)."
        )
    else:
        st.caption("🤖 ИИ выключен — нет ключа Anthropic.")
