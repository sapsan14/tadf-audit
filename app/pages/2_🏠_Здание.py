from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import streamlit as st  # noqa: E402

from app._state import get_current, set_current  # noqa: E402

st.title("Здание (auditi objekt)")

audit = get_current()
b = audit.building

# Scope widget state per-audit so reloading a different audit reseeds the form,
# and use explicit keys so +/- steppers persist across reruns.
scope = audit.id or "new"


def k(name: str) -> str:
    return f"b_{scope}_{name}"


b.address = st.text_input("Адрес объекта (Aadress)", value=b.address, key=k("address"))

col1, col2 = st.columns(2)
with col1:
    b.kataster_no = (
        st.text_input(
            "Katastritunnus",
            value=b.kataster_no or "",
            help="Например: 85101:004:0020",
            key=k("kataster_no"),
        )
        or None
    )
with col2:
    b.ehr_code = (
        st.text_input(
            "Ehitisregistri kood (EHR)",
            value=b.ehr_code or "",
            help="7–12 цифр",
            key=k("ehr_code"),
        )
        or None
    )

b.use_purpose = (
    st.text_input(
        "Kasutusotstarve (назначение)",
        value=b.use_purpose or "",
        help="Например: aiamaja, korterelamu, ärihoone",
        key=k("use_purpose"),
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
        step=1,
        key=k("construction_year"),
    )
with col2:
    _last = st.number_input(
        "Год последней реконструкции (0 = не было)",
        min_value=0,
        max_value=2100,
        value=b.last_renovation_year or 0,
        step=1,
        key=k("last_renovation_year"),
    )
    b.last_renovation_year = _last if _last > 0 else None
with col3:
    b.pre_2003 = st.checkbox(
        "Pre-2003 ehitis",
        value=b.pre_2003,
        help="EhSRS § 28 — аудит заменяет недостающую документацию",
        key=k("pre_2003"),
    )

st.subheader("Технические показатели (для §10 отчёта)")
col1, col2, col3 = st.columns(3)
with col1:
    _fp = st.number_input(
        "Ehitisealune pind (m²)",
        min_value=0.0,
        value=b.footprint_m2 or 0.0,
        step=0.5,
        format="%.1f",
        key=k("footprint_m2"),
    )
    b.footprint_m2 = _fp if _fp > 0 else None
with col2:
    _h = st.number_input(
        "Высота (m)",
        min_value=0.0,
        value=b.height_m or 0.0,
        step=0.1,
        format="%.1f",
        key=k("height_m"),
    )
    b.height_m = _h if _h > 0 else None
with col3:
    _vol = st.number_input(
        "Maht (m³)",
        min_value=0.0,
        value=b.volume_m3 or 0.0,
        step=1.0,
        format="%.1f",
        key=k("volume_m3"),
    )
    b.volume_m3 = _vol if _vol > 0 else None

col1, col2, col3 = st.columns(3)
with col1:
    _sa = st.number_input(
        "Этажей над землёй",
        min_value=0,
        max_value=50,
        value=b.storeys_above or 0,
        step=1,
        key=k("storeys_above"),
    )
    b.storeys_above = _sa if _sa > 0 else None
with col2:
    _sb = st.number_input(
        "Этажей под землёй",
        min_value=0,
        max_value=10,
        value=b.storeys_below or 0,
        step=1,
        key=k("storeys_below"),
    )
    b.storeys_below = _sb  # 0 is a valid answer for "no basement"
with col3:
    _site = st.number_input(
        "Kinnistu pindala (m²)",
        min_value=0.0,
        value=b.site_area_m2 or 0.0,
        step=10.0,
        format="%.1f",
        key=k("site_area_m2"),
    )
    b.site_area_m2 = _site if _site > 0 else None

st.subheader("Пожарная безопасность")
_fc_options = [None, "TP-1", "TP-2", "TP-3"]
b.fire_class = st.selectbox(
    "Tulepüsivusklass",
    options=_fc_options,
    index=_fc_options.index(b.fire_class) if b.fire_class in _fc_options else 0,
    format_func=lambda x: "(не указано)" if x is None else x,
    key=k("fire_class"),
)

st.subheader("Проектировщик / строитель")
col1, col2 = st.columns(2)
with col1:
    b.designer = (
        st.text_input("Designer (projekteerija)", value=b.designer or "", key=k("designer")) or None
    )
with col2:
    b.builder = (
        st.text_input("Builder (ehitaja)", value=b.builder or "", key=k("builder")) or None
    )

if b.pre_2003:
    b.substitute_docs_note = (
        st.text_area(
            "Substitute-docs note (EhSRS § 28)",
            value=b.substitute_docs_note or "",
            help="Заметка о том, какую документацию заменяет данный аудит",
            key=k("substitute_docs_note"),
        )
        or None
    )

audit.building = b
set_current(audit)
