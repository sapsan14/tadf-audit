from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / 'src'))

from datetime import date

import streamlit as st

from app._state import all_saved_audits, get_current, reload_from_db, set_current
from tadf.models import Auditor

st.title("Новый аудит / открыть существующий")

with st.expander("Открыть сохранённый аудит", expanded=False):
    saved = all_saved_audits()
    if saved:
        labels = [f"#{a.id} — {a.display_no()} — {a.building.address[:50]}" for a in saved]
        idx = st.selectbox(
            "Выберите аудит", options=range(len(saved)), format_func=lambda i: labels[i]
        )
        if st.button("Загрузить", type="primary"):
            reload_from_db(saved[idx].id)
            st.success(f"Загружен аудит #{saved[idx].id}")
            st.rerun()
    else:
        st.caption("Сохранённых аудитов пока нет.")

audit = get_current()

st.header("Метаданные аудита")

col1, col2, col3 = st.columns(3)
with col1:
    audit.seq_no = st.number_input("Порядковый номер (seq_no)", min_value=1, value=audit.seq_no)
with col2:
    audit.year = st.number_input("Год", min_value=2020, max_value=2099, value=audit.year)
with col3:
    audit.visit_date = st.date_input("Дата осмотра", value=audit.visit_date or date.today())

col1, col2 = st.columns(2)
with col1:
    audit.type = st.selectbox(
        "Тип (по имени файла)",
        options=["EA", "EP", "TJ", "TP", "AU"],
        index=["EA", "EP", "TJ", "TP", "AU"].index(audit.type),
        help="EA = Ehitise audit · EP = Ehitusprojekt audit · TJ = Tehniline järelevalve · TP = Tehniline projekt · AU = institutional",
    )
with col2:
    audit.subtype = st.selectbox(
        "Подтип (Auditi liik)",
        options=["kasutuseelne", "korraline", "erakorraline"],
        index=["kasutuseelne", "korraline", "erakorraline"].index(audit.subtype),
    )

audit.purpose = st.text_area(
    "Цель аудита (auditi eesmärk)",
    value=audit.purpose or "",
    height=100,
    help="Если оставите пусто — будет подставлено из стандартного шаблона по подтипу.",
)
audit.scope = st.text_area(
    "Область аудита (auditi ulatus)",
    value=audit.scope or "",
    height=100,
)

st.header("Аудиторы")
st.caption(
    "В отчёте всегда два лица: koostaja (составитель) и kontrollija / vastutav pädev isik (ответственный)."
)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Auditi koostas")
    audit.composer = Auditor(
        full_name=st.text_input("Имя", value=audit.composer.full_name, key="composer_name"),
        company=st.text_input(
            "Компания", value=audit.composer.company or "", key="composer_company"
        ),
        company_reg_nr=st.text_input(
            "Reg. nr", value=audit.composer.company_reg_nr or "", key="composer_reg"
        )
        or None,
        qualification=st.text_input(
            "Квалификация", value=audit.composer.qualification or "", key="composer_qual"
        )
        or None,
    )
with col2:
    st.subheader("Auditi kontrollis (vastutav pädev isik)")
    audit.reviewer = Auditor(
        full_name=st.text_input("Имя", value=audit.reviewer.full_name, key="reviewer_name"),
        kutsetunnistus_no=st.text_input(
            "Kutsetunnistus №", value=audit.reviewer.kutsetunnistus_no or "", key="reviewer_kut"
        )
        or None,
        qualification=st.text_input(
            "Квалификация",
            value=audit.reviewer.qualification or "Diplomeeritud insener tase 7",
            key="reviewer_qual",
        )
        or None,
        company=st.text_input(
            "Компания", value=audit.reviewer.company or "TADF", key="reviewer_company"
        )
        or None,
    )

st.header("Заказчик (Tellija)")
if audit.client is None:
    from tadf.models import Client
    audit.client = Client(name="")
audit.client.name = st.text_input("Название / имя", value=audit.client.name)
col1, col2, col3 = st.columns(3)
with col1:
    audit.client.reg_code = st.text_input("Reg. kood", value=audit.client.reg_code or "") or None
with col2:
    audit.client.contact_email = (
        st.text_input("E-mail", value=audit.client.contact_email or "") or None
    )
with col3:
    audit.client.contact_phone = (
        st.text_input("Телефон", value=audit.client.contact_phone or "") or None
    )
audit.client.address = st.text_input("Адрес заказчика", value=audit.client.address or "") or None

set_current(audit)
st.success(f"Текущий номер: **{audit.display_no()}** ({audit.type} / {audit.subtype})")
