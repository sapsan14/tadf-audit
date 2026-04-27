from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from datetime import date  # noqa: E402

import streamlit as st  # noqa: E402

from app._state import (  # noqa: E402
    all_saved_drafts,
    delete_audit_by_id,
    get_current,
    reload_from_db,
    set_current,
    start_new_draft,
)
from app._widgets import flush_improve_pending, improve_button_for  # noqa: E402
from tadf.api.imports import (  # noqa: E402
    list_pending,
    map_teatmik,
    mark_applied,
    mark_rejected,
)
from tadf.api.tokens import issue as _issue_token  # noqa: E402
from tadf.external.links import teatmik_company_url  # noqa: E402
from tadf.models import Auditor  # noqa: E402

flush_improve_pending()

st.title("Аудит — черновики и текущая работа")

# ---------------------------------------------------------------------------
# Drafts manager — list/load/delete sits at the top of this page so the
# auditor sees everything they're working on as soon as they open the form.
# Only `status='draft'` rows are listed; signed/submitted audits are hidden
# (they don't need to be re-edited and shouldn't be casually deletable).
# ---------------------------------------------------------------------------
with st.container(border=True):
    drafts = all_saved_drafts()
    loaded_id = st.session_state.get("loaded_id")

    head1, head2 = st.columns([3, 1])
    head1.subheader(f"📋 Сохранённые черновики ({len(drafts)})")
    if head2.button(
        "➕ Новый аудит",
        key="drafts_new_btn",
        use_container_width=True,
        help="Очистить форму и начать новый черновик с нуля.",
    ):
        start_new_draft()
        st.rerun()

    if not drafts:
        st.caption(
            "Черновиков пока нет — заполните форму ниже и сохраните на странице "
            "**📄 Готовый отчёт** кнопкой «💾 Сохранить черновик»."
        )
    else:
        for d in drafts:
            is_current = d.id == loaded_id
            with st.container(border=is_current):
                cc1, cc2, cc3, cc4 = st.columns([5, 2, 1, 1])
                addr = (d.building.address or "").strip() or "(адрес не введён)"
                updated = d.updated_at.strftime("%Y-%m-%d %H:%M") if d.updated_at else "—"
                cc1.markdown(
                    f"**#{d.id} · {d.display_no()}** — {addr[:80]}  \n"
                    f"<small>{d.subtype} · {d.type} · обновлён {updated}</small>",
                    unsafe_allow_html=True,
                )
                cc2.markdown(
                    f"<small>наблюдений: **{len(d.findings)}**, фото: **{len(d.photos)}**</small>",
                    unsafe_allow_html=True,
                )
                if is_current:
                    cc3.markdown("✅<br/><small>тек.</small>", unsafe_allow_html=True)
                else:
                    if cc3.button(
                        "📂",
                        key=f"draft_load_{d.id}",
                        help="Загрузить этот черновик в форму",
                        use_container_width=True,
                    ):
                        reload_from_db(d.id)
                        st.rerun()

                pending_key = f"_draft_del_confirm_{d.id}"
                if st.session_state.get(pending_key):
                    if cc4.button(
                        "✓",
                        key=f"draft_del_ok_{d.id}",
                        type="primary",
                        help="Подтвердить удаление",
                        use_container_width=True,
                    ):
                        delete_audit_by_id(d.id)
                        st.session_state.pop(pending_key, None)
                        if loaded_id == d.id:
                            start_new_draft()
                        st.rerun()
                    if st.button(
                        "Отмена",
                        key=f"draft_del_cancel_{d.id}",
                    ):
                        st.session_state.pop(pending_key, None)
                        st.rerun()
                else:
                    if cc4.button(
                        "🗑️",
                        key=f"draft_del_{d.id}",
                        help="Удалить черновик (с подтверждением)",
                        use_container_width=True,
                    ):
                        st.session_state[pending_key] = True
                        st.rerun()

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
improve_button_for(
    text=audit.purpose or "",
    state_key_prefix=f"imp_purpose_{scope}",
    section_ref="3",
    text_widget_key=k("purpose"),
    apply=lambda v: setattr(audit, "purpose", v),
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
improve_button_for(
    text=audit.scope or "",
    state_key_prefix=f"imp_scope_{scope}",
    section_ref="3",
    text_widget_key=k("scope"),
    apply=lambda v: setattr(audit, "scope", v),
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
improve_button_for(
    text=audit.client.address or "",
    state_key_prefix=f"imp_client_addr_{scope}",
    section_ref=None,
    text_widget_key=k("client_addr"),
    apply=lambda v: setattr(audit.client, "address", v),
)

# Teatmik deep-link. URL fragment carries `&target=client` so the
# in-browser helper sends a hint and we apply directly to the client
# bundle (name + reg_code + address + email + phone) on the Новый аудит
# page below — no designer/builder/client picker.
# The button is ALWAYS rendered: when there's no name/reg-code yet, it
# renders disabled with a hint so the auditor sees the integration exists.
_tk_query = (audit.client.reg_code or audit.client.name or "").strip()
_tk_link = teatmik_company_url(_tk_query) if _tk_query else None
if _tk_link:
    if audit.id is not None:
        token = _issue_token(audit.id)
        sep = "&" if "#" in _tk_link else "#"
        _tk_link = f"{_tk_link}{sep}tadf={token}&target=client"
        _tk_label = "🔎 Найти в Teatmik (авто-импорт)"
    else:
        _tk_label = "🔎 Найти в Teatmik (без авто-импорта — сохрани аудит)"
    st.link_button(_tk_label, _tk_link)
else:
    st.button(
        "🔎 Найти в Teatmik",
        disabled=True,
        key=f"teatmik_client_disabled_{scope}",
        help=(
            "Введите название заказчика или его рег-код выше — "
            "ссылка на Teatmik активируется."
        ),
    )
st.caption(
    "💡 Импорт работает после установки bookmarklet / Tampermonkey — "
    "см. страницу **🔌 Подключения**."
)

# ---------------------------------------------------------------------------
# 📥 Pending imports from Teatmik bookmarklet/userscript with target=client.
# Shown on this page so the auditor sees the result where they triggered it.
# Other targets (designer/builder) live on the Здание page.
#
# @st.fragment(run_every="5s") makes Streamlit re-poll pending_import every
# 5 seconds without user interaction — so when the auditor returns from
# Teatmik (where the bookmarklet POSTed an import), the row appears here
# automatically instead of only after they click something else.
# Apply uses st.rerun(scope="app") so the client widgets reseed properly.
# ---------------------------------------------------------------------------


@st.fragment(run_every="5s")
def _render_pending_client_imports() -> None:
    if audit.id is None:
        return
    _client_imports = [
        imp for imp in list_pending(audit.id)
        if imp.kind == "teatmik" and imp.payload.get("target") == "client"
    ]
    for imp in _client_imports:
        mapped = map_teatmik(imp.payload)
        mapped.pop("target", None)
        with st.container(border=True):
            st.markdown(
                f"📥 **Импорт из Teatmik → клиент** — "
                f"{imp.received_at.strftime('%H:%M:%S')}"
            )
            if imp.source_url:
                st.caption(f"Источник: {imp.source_url}")
            if not mapped:
                st.warning("Пустая карточка компании.")
            else:
                st.write("Найдено:")
                for kfield, val in mapped.items():
                    st.write(f"- `{kfield}`: {val}")
            ca, cr = st.columns([1, 1])
            if ca.button("✅ Применить к клиенту", type="primary", key=f"imp_client_apply_{imp.id}"):
                if audit.client is None:
                    from tadf.models import Client as _Client
                    audit.client = _Client(name="")
                if mapped.get("name"):
                    audit.client.name = mapped["name"]
                if mapped.get("reg_code"):
                    audit.client.reg_code = mapped["reg_code"]
                if mapped.get("address"):
                    audit.client.address = mapped["address"]
                if mapped.get("email"):
                    audit.client.contact_email = mapped["email"]
                if mapped.get("phone"):
                    audit.client.contact_phone = mapped["phone"]
                set_current(audit)
                # Pop widget keys so client form re-seeds from new model values.
                for w in (
                    k("client_name"), k("client_reg"), k("client_email"),
                    k("client_phone"), k("client_addr"),
                ):
                    st.session_state.pop(w, None)
                mark_applied(imp.id)
                st.rerun(scope="app")
            if cr.button("❌ Отклонить", key=f"imp_client_reject_{imp.id}"):
                mark_rejected(imp.id)
                st.rerun(scope="app")


_render_pending_client_imports()

set_current(audit)
st.success(f"Текущий номер: **{audit.display_no()}** ({audit.type} / {audit.subtype})")
