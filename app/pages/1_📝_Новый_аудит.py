from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from datetime import date  # noqa: E402

import streamlit as st  # noqa: E402

from app._state import all_saved_audits, get_current, reload_from_db, set_current  # noqa: E402
from tadf.api.tokens import issue as _issue_token  # noqa: E402
from tadf.external.links import teatmik_company_url  # noqa: E402
from tadf.models import Auditor  # noqa: E402

st.title("Новый аудит / открыть существующий")

with st.expander("Открыть сохранённый аудит", expanded=False):
    saved = all_saved_audits()
    if saved:
        labels = [f"#{a.id} — {a.display_no()} — {a.building.address[:50]}" for a in saved]
        idx = st.selectbox("Выберите аудит", options=range(len(saved)), format_func=lambda i: labels[i])
        if st.button("Загрузить", type="primary"):
            reload_from_db(saved[idx].id)
            st.success(f"Загружен аудит #{saved[idx].id}")
            st.rerun()
    else:
        st.caption("Сохранённых аудитов пока нет.")

audit = get_current()
scope = audit.id or "new"


def k(name: str) -> str:
    return f"a_{scope}_{name}"


st.header("Метаданные аудита")

col1, col2, col3 = st.columns(3)
with col1:
    audit.seq_no = st.number_input(
        "Порядковый номер (seq_no)",
        min_value=1,
        value=audit.seq_no,
        step=1,
        key=k("seq_no"),
        help=(
            "Номер работы внутри года, нумерация ваша (например 12). "
            "Попадёт в имя файла отчёта и в раздел «Töö nr» титульного листа."
        ),
    )
with col2:
    audit.year = st.number_input(
        "Год",
        min_value=2020,
        max_value=2099,
        value=audit.year,
        step=1,
        key=k("year"),
        help="Год составления отчёта (используется в номере работы).",
    )
with col3:
    audit.visit_date = st.date_input(
        "Дата осмотра",
        value=audit.visit_date or date.today(),
        key=k("visit_date"),
        help=(
            "Дата визуального осмотра объекта (paikvaatluse kuupäev) — "
            "обязательное поле по §5 Ehitise auditi tegemise kord. "
            "Указывается в разделе 4 отчёта."
        ),
    )

col1, col2 = st.columns(2)
with col1:
    audit.type = st.selectbox(
        "Тип (по имени файла)",
        options=["EA", "EP", "TJ", "TP", "AU"],
        index=["EA", "EP", "TJ", "TP", "AU"].index(audit.type),
        help=(
            "Кодировка типа аудита, попадает в имя файла:\n"
            "• EA — Ehitise audit (общий аудит здания)\n"
            "• EP — Ehitusprojekti audit (аудит проекта)\n"
            "• TJ — Tehniline järelevalve (тех. надзор)\n"
            "• TP — Tehniline projekt (аудит тех. проекта)\n"
            "• AU — институциональный аудит (больница, школа и т.п.)"
        ),
        key=k("type"),
    )
with col2:
    audit.subtype = st.selectbox(
        "Подтип (Auditi liik)",
        options=["kasutuseelne", "korraline", "erakorraline"],
        index=["kasutuseelne", "korraline", "erakorraline"].index(audit.subtype),
        help=(
            "Per Ehitusseadustik §18:\n"
            "• kasutuseelne — перед получением касутуслоа (новые здания / "
            "изменение назначения)\n"
            "• korraline — плановая периодическая проверка существующего здания\n"
            "• erakorraline — внеплановая проверка по конкретному событию "
            "(авария, шторм, сомнение в безопасности)"
        ),
        key=k("subtype"),
    )

audit.purpose = st.text_area(
    "Цель аудита (auditi eesmärk)",
    value=audit.purpose or "",
    height=100,
    help=(
        "По §5 Ehitise auditi tegemise kord обязательное поле. "
        "Опишите, ЗАЧЕМ заказчик заказал аудит и что он должен показать. "
        "Если оставите пусто — программа подставит стандартный текст по подтипу."
    ),
    key=k("purpose"),
)
audit.scope = st.text_area(
    "Область аудита (auditi ulatus)",
    value=audit.scope or "",
    height=100,
    help=(
        "По §5 — что именно проверяется: какие конструкции, какие "
        "техносистемы, есть ли проверка пожарной безопасности и т.д. "
        "Это то, что НЕ проверяется, тоже здесь стоит указать чтобы избежать "
        "позднейших претензий."
    ),
    key=k("scope"),
)

st.header("Аудиторы")
st.caption(
    "В отчёте всегда два лица: koostaja (составитель) и kontrollija / vastutav pädev isik (ответственный)."
)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Auditi koostas")
    st.caption("Инженер, который физически готовит отчёт. Может совпадать с проверяющим.")
    audit.composer = Auditor(
        full_name=st.text_input(
            "Имя",
            value=audit.composer.full_name,
            key=k("composer_name"),
            help="ФИО составителя.",
        ),
        company=st.text_input(
            "Компания",
            value=audit.composer.company or "",
            key=k("composer_company"),
            help="Юр. лицо составителя (например TADF Ehitus OÜ или UNTWERP OÜ).",
        ) or None,
        company_reg_nr=st.text_input(
            "Reg. nr",
            value=audit.composer.company_reg_nr or "",
            key=k("composer_reg"),
            help="Регистрационный код компании составителя (8 цифр для OÜ).",
        ) or None,
        qualification=st.text_input(
            "Квалификация",
            value=audit.composer.qualification or "",
            key=k("composer_qual"),
            help="Например «Diplomeeritud ehitusinsener tase 7».",
        ) or None,
    )
with col2:
    st.subheader("Auditi kontrollis (vastutav pädev isik)")
    st.caption(
        "Сертифицированное лицо (kutsetunnistus), которое юридически отвечает "
        "за отчёт и подписывает его. По умолчанию — Фёдор."
    )
    audit.reviewer = Auditor(
        full_name=st.text_input(
            "Имя",
            value=audit.reviewer.full_name,
            key=k("reviewer_name"),
            help="ФИО ответственного лица (vastutav pädev isik).",
        ),
        kutsetunnistus_no=st.text_input(
            "Kutsetunnistus №",
            value=audit.reviewer.kutsetunnistus_no or "",
            key=k("reviewer_kut"),
            help=(
                "Номер kutsetunnistus — обязательное поле по §5. У Фёдора 148515. "
                "Проверить актуальность можно на kutsekoda.ee."
            ),
        ) or None,
        qualification=st.text_input(
            "Квалификация",
            value=audit.reviewer.qualification or "Diplomeeritud insener tase 7",
            key=k("reviewer_qual"),
        ) or None,
        company=st.text_input(
            "Компания",
            value=audit.reviewer.company or "TADF Ehitus OÜ",
            key=k("reviewer_company"),
        ) or None,
    )

st.header("Заказчик (Tellija)")
st.caption("Лицо или организация, заказавшая аудит. Указывается на титульном листе.")
if audit.client is None:
    from tadf.models import Client

    audit.client = Client(name="")
audit.client.name = st.text_input(
    "Название / имя",
    value=audit.client.name,
    key=k("client_name"),
    help="Название организации или ФИО физ. лица.",
)
col1, col2, col3 = st.columns(3)
with col1:
    audit.client.reg_code = st.text_input(
        "Reg. kood",
        value=audit.client.reg_code or "",
        key=k("client_reg"),
        help="Регистрационный код юр. лица заказчика (если есть). Для физ. лица оставить пустым.",
    ) or None
with col2:
    audit.client.contact_email = st.text_input(
        "E-mail", value=audit.client.contact_email or "", key=k("client_email")
    ) or None
with col3:
    audit.client.contact_phone = st.text_input(
        "Телефон", value=audit.client.contact_phone or "", key=k("client_phone")
    ) or None
audit.client.address = st.text_input(
    "Адрес заказчика",
    value=audit.client.address or "",
    key=k("client_addr"),
    help="Адрес для переписки с заказчиком (может отличаться от адреса объекта).",
) or None

# Teatmik deep-link. If the audit is saved (audit.id), embed the per-audit
# import token so the in-browser helper (bookmarklet / Tampermonkey
# userscript) auto-fills client.name/reg_code/address back here.
_tk_query = audit.client.reg_code or audit.client.name
if _tk_query and _tk_query.strip():
    link = teatmik_company_url(_tk_query)
    if link:
        if audit.id is not None:
            token = _issue_token(audit.id)
            sep = "&" if "#" in link else "#"
            link = f"{link}{sep}tadf={token}"
            label = "🔎 Найти в Teatmik (авто-импорт)"
        else:
            label = "🔎 Найти в Teatmik (без авто-импорта — сохрани аудит)"
        st.link_button(label, link)
        st.caption(
            "💡 Импорт работает после установки bookmarklet / Tampermonkey — "
            "см. страницу **🔌 Подключения**."
        )

set_current(audit)
st.success(f"Текущий номер: **{audit.display_no()}** ({audit.type} / {audit.subtype})")
