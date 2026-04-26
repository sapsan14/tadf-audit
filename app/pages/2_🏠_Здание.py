from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / 'src'))

import streamlit as st

from app._state import get_current, set_current
from tadf.models import Building

st.title("Здание (auditi objekt)")

audit = get_current()
b = audit.building

b.address = st.text_input("Адрес объекта (Aadress)", value=b.address)

col1, col2 = st.columns(2)
with col1:
    b.kataster_no = (
        st.text_input(
            "Katastritunnus",
            value=b.kataster_no or "",
            help="Например: 85101:004:0020",
        )
        or None
    )
with col2:
    b.ehr_code = (
        st.text_input(
            "Ehitisregistri kood (EHR)",
            value=b.ehr_code or "",
            help="7–12 цифр",
        )
        or None
    )

b.use_purpose = (
    st.text_input(
        "Kasutusotstarve (назначение)",
        value=b.use_purpose or "",
        help="Например: aiamaja, korterelamu, ärihoone",
    )
    or None
)

col1, col2, col3 = st.columns(3)
with col1:
    b.construction_year = st.number_input(
        "Год постройки",
        min_value=1800,
        max_value=2100,
        value=b.construction_year or 2000,
    )
with col2:
    b.last_renovation_year = (
        st.number_input(
            "Год последней реконструкции",
            min_value=0,
            max_value=2100,
            value=b.last_renovation_year or 0,
        )
        or None
    )
with col3:
    b.pre_2003 = st.checkbox(
        "Pre-2003 ehitis",
        value=b.pre_2003,
        help="EhSRS § 28 — аудит заменяет недостающую документацию",
    )

st.subheader("Технические показатели (для §10 отчёта)")
col1, col2, col3 = st.columns(3)
with col1:
    b.footprint_m2 = (
        st.number_input(
            "Ehitisealune pind (m²)", min_value=0.0, value=b.footprint_m2 or 0.0, format="%.1f"
        )
        or None
    )
with col2:
    b.height_m = (
        st.number_input("Высота (m)", min_value=0.0, value=b.height_m or 0.0, format="%.1f") or None
    )
with col3:
    b.volume_m3 = (
        st.number_input("Maht (m³)", min_value=0.0, value=b.volume_m3 or 0.0, format="%.1f") or None
    )

col1, col2, col3 = st.columns(3)
with col1:
    b.storeys_above = st.number_input("Этажей над землёй", min_value=0, value=b.storeys_above or 0)
with col2:
    b.storeys_below = st.number_input("Этажей под землёй", min_value=0, value=b.storeys_below or 0)
with col3:
    b.site_area_m2 = (
        st.number_input(
            "Kinnistu pindala (m²)", min_value=0.0, value=b.site_area_m2 or 0.0, format="%.1f"
        )
        or None
    )

st.subheader("Пожарная безопасность")
b.fire_class = st.selectbox(
    "Tulepüsivusklass",
    options=[None, "TP-1", "TP-2", "TP-3"],
    index=[None, "TP-1", "TP-2", "TP-3"].index(b.fire_class)
    if b.fire_class in (None, "TP-1", "TP-2", "TP-3")
    else 0,
    format_func=lambda x: "(не указано)" if x is None else x,
)

st.subheader("Проектировщик / строитель")
col1, col2 = st.columns(2)
with col1:
    b.designer = st.text_input("Designer (projekteerija)", value=b.designer or "") or None
with col2:
    b.builder = st.text_input("Builder (ehitaja)", value=b.builder or "") or None

if b.pre_2003:
    b.substitute_docs_note = (
        st.text_area(
            "Substitute-docs note (EhSRS § 28)",
            value=b.substitute_docs_note or "",
            help="Заметка о том, какую документацию заменяет данный аудит",
        )
        or None
    )

audit.building = Building(**b.model_dump())
set_current(audit)
