from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / 'src'))

import streamlit as st

from app._state import get_current, set_current
from tadf.legal.loader import for_section
from tadf.models import Finding

st.title("Находки и наблюдения")

audit = get_current()

SECTION_OPTIONS = [
    ("4", "4. Hoone ülevaatus"),
    ("5", "5. Arhitektuur"),
    ("6", "6. Konstruktiivne osa"),
    ("6.1", "6.1. Vundament"),
    ("6.2", "6.2. Välisseinad"),
    ("6.3", "6.3. Vahelaed"),
    ("6.4", "6.4. Katus"),
    ("6.5", "6.5. Viimistlus"),
    ("6.6", "6.6. Aknad ja uksed"),
    ("7", "7. Tehnosüsteemid"),
    ("7.1", "7.1. Veevarustus ja kanalisatsioon"),
    ("7.2", "7.2. Elektrivarustus"),
    ("7.3", "7.3. Küte ja ventilatsioon"),
    ("8", "8. Tulekaitse"),
    ("11", "11. KOKKUVÕTE — только аудитор, без ИИ"),
    ("14", "14. LÕPPHINNANG — только аудитор, без ИИ"),
]
SECTION_KEYS = [s[0] for s in SECTION_OPTIONS]
SECTION_LABELS = dict(SECTION_OPTIONS)

st.subheader("Добавить находку")
with st.form("new_finding", clear_on_submit=True):
    col1, col2 = st.columns([1, 3])
    with col1:
        section = st.selectbox(
            "Раздел",
            options=SECTION_KEYS,
            format_func=lambda k: SECTION_LABELS[k],
        )
        severity = st.selectbox(
            "Серьёзность",
            options=["info", "nonconf_minor", "nonconf_major", "hazard"],
            format_func=lambda s: {
                "info": "📝 Инфо",
                "nonconf_minor": "⚠️ Мелкое несоответствие",
                "nonconf_major": "❗ Существенное несоответствие",
                "hazard": "🛑 Опасность",
            }[s],
        )
    with col2:
        observation = st.text_area(
            "Наблюдение (тезисами или прозой; на эстонском)",
            height=100,
        )
        recommendation = st.text_area(
            "Рекомендация (опционально)",
            height=60,
        )

    # Suggested legal refs for this section
    suggestions = for_section(section.split(".")[0], audit.type)
    legal_codes = []
    if suggestions:
        legal_codes = st.multiselect(
            "Ссылки на закон (предложения для этого раздела)",
            options=[r.code for r in suggestions],
            format_func=lambda c: (
                f"{c} — {next(r.title_et for r in suggestions if r.code == c)[:60]}"
            ),
        )

    submitted = st.form_submit_button("Добавить находку", type="primary")
    if submitted and observation.strip():
        audit.findings.append(
            Finding(
                section_ref=section,
                severity=severity,
                observation_raw=observation.strip(),
                recommendation=recommendation.strip() or None,
                legal_ref_codes=legal_codes,
            )
        )
        set_current(audit)
        st.success("Находка добавлена")

st.subheader(f"Все находки ({len(audit.findings)})")
if not audit.findings:
    st.caption(
        "Пока нет находок. Добавьте хотя бы одну в каждый из обязательных разделов: 11 (Kokkuvõte) и 14 (Lõpphinnang)."
    )

for i, f in enumerate(audit.findings):
    title = f"{i + 1}. [{f.section_ref}] {f.observation_raw[:80]}"
    with st.expander(title):
        st.write(f"**Раздел:** {SECTION_LABELS.get(f.section_ref, f.section_ref)}")
        st.write(f"**Серьёзность:** {f.severity}")
        st.write(f"**Наблюдение:** {f.observation_raw}")
        if f.recommendation:
            st.write(f"**Рекомендация:** {f.recommendation}")
        if f.legal_ref_codes:
            st.write(f"**Ссылки:** {', '.join(f.legal_ref_codes)}")
        if st.button("Удалить", key=f"del_{i}"):
            audit.findings.pop(i)
            set_current(audit)
            st.rerun()
