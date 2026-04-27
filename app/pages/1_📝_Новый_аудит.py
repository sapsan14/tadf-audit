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
    clone_as_new_draft,
    delete_audit_by_id,
    ensure_draft_saved,
    get_current,
    list_audit_snapshots,
    reload_from_db,
    restore_audit_snapshot,
    set_current,
    start_new_draft,
)
from app._widgets import (  # noqa: E402
    _PENDING_PREFIX,
    address_picker,
    autofill_from_picker,
    client_picker,
    combobox,
    flush_improve_pending,
    hint_caption,
    improve_button_for,
)
from tadf import feature_flags  # noqa: E402
from tadf.api.imports import (  # noqa: E402
    list_pending,
    map_teatmik,
    mark_applied,
    mark_rejected,
)
from tadf.api.tokens import issue as _issue_token  # noqa: E402
from tadf.db.lookups import (  # noqa: E402
    client_names,
    composer_companies,
    composer_names,
    latest_auditor_by_name,
    latest_client_by_name,
)
from tadf.external.links import teatmik_company_url  # noqa: E402
from tadf.external.registry_codes import reg_code_hint  # noqa: E402
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
                cc1, cc2, cc3, cc4, cc5 = st.columns([5, 2, 1, 1, 1])
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

                if cc4.button(
                    "📑",
                    key=f"draft_clone_{d.id}",
                    help=(
                        "Клонировать как новый черновик: "
                        "сохраняются аудиторы, тип и подтип, методология; "
                        "сбрасываются адрес/EHR/кадастр, заказчик, наблюдения, "
                        "фото, дата осмотра."
                    ),
                    use_container_width=True,
                ):
                    clone_as_new_draft(d.id)
                    st.success(f"Черновик клонирован из #{d.id}")
                    st.rerun()

                pending_key = f"_draft_del_confirm_{d.id}"
                if st.session_state.get(pending_key):
                    if cc5.button(
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
                    if cc5.button(
                        "🗑️",
                        key=f"draft_del_{d.id}",
                        help="Удалить черновик (с подтверждением)",
                        use_container_width=True,
                    ):
                        st.session_state[pending_key] = True
                        st.rerun()

                # 🕘 History — show last 30 snapshots; click any version
                # to restore. Auto-save writes a fresh snapshot on every
                # meaningful state change, so this list is the auditor's
                # safety net against accidental edits.
                snaps = list_audit_snapshots(d.id)
                if snaps:
                    with st.expander(f"🕘 История ({len(snaps)})", expanded=False):
                        st.caption(
                            "Каждая запись — снимок состояния на момент авто-сохранения. "
                            "Нажмите «Восстановить», чтобы откатиться (можно потом откатить откат — "
                            "сам restore тоже создаёт новую запись)."
                        )
                        for snap_id, version_no, created_at in snaps:
                            sc1, sc2, sc3 = st.columns([2, 4, 2])
                            sc1.markdown(f"**v{version_no}**")
                            sc2.markdown(
                                f"<small>{created_at.strftime('%Y-%m-%d %H:%M:%S')}</small>",
                                unsafe_allow_html=True,
                            )
                            if sc3.button(
                                "↩️ Восстановить",
                                key=f"snap_restore_{d.id}_{snap_id}",
                                use_container_width=True,
                            ):
                                if restore_audit_snapshot(snap_id):
                                    st.success(f"Восстановлен v{version_no}")
                                    st.rerun()
                                else:
                                    st.error("Не удалось восстановить (повреждённый снимок)")

audit = get_current()
scope = audit.id or "new"


def k(name: str) -> str:
    return f"a_{scope}_{name}"


# ---------------------------------------------------------------------------
# Auto-fill on combobox-pick — watches the three name comboboxes (composer,
# reviewer, client) and re-seeds sibling-field widget keys from the most
# recent matching DB row. Runs BEFORE the form widgets render so the
# pending-widget machinery (`flush_improve_pending`) can apply the values
# on the next rerun without Streamlit's "widget already instantiated" error.
# ---------------------------------------------------------------------------
_COMPOSER_AUTOFILL = {
    "kutsetunnistus_no": k("composer_kut"),
    "qualification": k("composer_qual"),
    "company": k("composer_company"),
    "company_reg_nr": k("composer_reg"),
}
_REVIEWER_AUTOFILL = {
    "kutsetunnistus_no": k("reviewer_kut"),
    "qualification": k("reviewer_qual"),
    "company": k("reviewer_company"),
    "company_reg_nr": k("reviewer_reg"),
}
_CLIENT_AUTOFILL = {
    "reg_code": k("client_reg"),
    "contact_email": k("client_email"),
    "contact_phone": k("client_phone"),
    "address": k("client_addr"),
}
if audit.client is None:
    from tadf.models import Client

    audit.client = Client(name="")


def _apply_to_composer(field: str, value: object) -> None:
    setattr(audit.composer, field, value)


def _apply_to_reviewer(field: str, value: object) -> None:
    setattr(audit.reviewer, field, value)


def _apply_to_client(field: str, value: object) -> None:
    setattr(audit.client, field, value)


# Pass the model's current name (NOT the widget-state key). Reading the
# model survives the `scope` flip from "new" → audit.id that happens on
# the first ensure_draft_saved — under "new" scope the typed name lives
# in `a_new_*_name`, but on the next render the widget key becomes
# `a_<id>_*_name` (still empty), so a widget-state lookup would bail and
# autofill would never fire.
autofill_from_picker(
    slot=f"composer_{scope}",
    picked_name=audit.composer.full_name if audit.composer else None,
    field_to_widget=_COMPOSER_AUTOFILL,
    fetch=latest_auditor_by_name,
    apply_to_model=_apply_to_composer,
)
autofill_from_picker(
    slot=f"reviewer_{scope}",
    picked_name=audit.reviewer.full_name if audit.reviewer else None,
    field_to_widget=_REVIEWER_AUTOFILL,
    fetch=latest_auditor_by_name,
    apply_to_model=_apply_to_reviewer,
)
autofill_from_picker(
    slot=f"client_{scope}",
    picked_name=audit.client.name if audit.client else None,
    field_to_widget=_CLIENT_AUTOFILL,
    fetch=latest_client_by_name,
    apply_to_model=_apply_to_client,
)


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
# Both auditor blocks render the SAME 5 fields in the SAME order so the
# rows line up horizontally between «Auditi koostas» and «Auditi
# kontrollis». A composer typically has empty Kutsetunnistus; a reviewer
# typically has empty Reg. nr (same firm as composer) — that's fine,
# the layout stays symmetric.
with col1:
    st.subheader("Auditi koostas")
    # Two lines so this caption matches the height of the right-hand
    # «kontrollis» caption — without padding, the form fields below
    # start at different baselines and the columns look misaligned.
    st.caption(
        "Инженер, который физически готовит отчёт. "
        "Может совпадать с проверяющим (тогда продублируйте поля справа)."
    )
    audit.composer = Auditor(
        full_name=combobox(
            "Имя",
            suggestions=composer_names(),
            value=audit.composer.full_name,
            key=k("composer_name"),
            help="ФИО составителя. Подсказки — из прошлых аудитов.",
        ) or "",
        kutsetunnistus_no=st.text_input(
            "Kutsetunnistus №",
            value=audit.composer.kutsetunnistus_no or "",
            key=k("composer_kut"),
            help="Если у составителя нет kutsetunnistus — оставьте пустым.",
        ) or None,
        qualification=st.text_input(
            "Квалификация",
            value=audit.composer.qualification or "",
            key=k("composer_qual"),
            help="Например «Diplomeeritud ehitusinsener tase 7».",
        ) or None,
        company=combobox(
            "Компания",
            suggestions=composer_companies(),
            value=audit.composer.company,
            key=k("composer_company"),
            help="Юр. лицо составителя (например TADF Ehitus OÜ).",
        ),
        company_reg_nr=(
            _composer_reg := st.text_input(
                "Reg. nr",
                value=audit.composer.company_reg_nr or "",
                key=k("composer_reg"),
                help="Регистрационный код компании составителя (8 цифр для OÜ).",
            )
        ) or None,
    )
    hint_caption(reg_code_hint(_composer_reg))
with col2:
    st.subheader("Auditi kontrollis (vastutav pädev isik)")
    st.caption(
        "Сертифицированное лицо (kutsetunnistus), которое юридически отвечает "
        "за отчёт и подписывает его. По умолчанию — Фёдор."
    )
    audit.reviewer = Auditor(
        full_name=combobox(
            "Имя",
            suggestions=composer_names(),
            value=audit.reviewer.full_name,
            key=k("reviewer_name"),
            help="ФИО ответственного лица (vastutav pädev isik).",
        ) or "",
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
        company=combobox(
            "Компания",
            suggestions=composer_companies(),
            value=audit.reviewer.company or "TADF Ehitus OÜ",
            key=k("reviewer_company"),
        ),
        company_reg_nr=(
            _reviewer_reg := st.text_input(
                "Reg. nr",
                value=audit.reviewer.company_reg_nr or "",
                key=k("reviewer_reg"),
                help="Если совпадает с компанией составителя — оставьте пустым.",
            )
        ) or None,
    )
    hint_caption(reg_code_hint(_reviewer_reg))

st.header("Заказчик (Tellija)")
st.caption("Лицо или организация, заказавшая аудит. Указывается на титульном листе.")
if audit.client is None:
    from tadf.models import Client

    audit.client = Client(name="")


def _apply_to_client(payload: dict, *, rerun_scope: str | None = None) -> None:
    """Apply external client data (Ariregister hit or Teatmik import) to
    the audit.client model AND seed the corresponding widget keys via the
    pending-widget queue so values appear in the form immediately on the
    next rerun — no «leave the page and come back» dance.

    Pending writes flow through `flush_improve_pending()` at the page top,
    same path used by the «✨ Улучшить» accept buttons and
    `autofill_from_picker`. Streamlit-safe across reruns and across the
    `scope` ("new" → audit.id) flip on the first save.
    """
    if audit.client is None:
        from tadf.models import Client as _Client
        audit.client = _Client(name="")
    if payload.get("name"):
        audit.client.name = payload["name"]
    if payload.get("reg_code"):
        audit.client.reg_code = payload["reg_code"]
    if payload.get("address"):
        audit.client.address = payload["address"]
    if payload.get("contact_email") or payload.get("email"):
        audit.client.contact_email = payload.get("contact_email") or payload.get("email")
    if payload.get("contact_phone") or payload.get("phone"):
        audit.client.contact_phone = payload.get("contact_phone") or payload.get("phone")

    set_current(audit)
    ensure_draft_saved(audit)  # mirrors into DirectoryClientRow + assigns audit.id

    # Re-scope here in case ensure_draft_saved just promoted a fresh draft
    # (audit.id went None → number). The widgets in the *next* render will
    # use this new scope for their keys, so the pending writes must too.
    _scope = audit.id or "new"
    queued = {
        f"a_{_scope}_client_name":  audit.client.name or "",
        f"a_{_scope}_client_reg":   audit.client.reg_code or "",
        f"a_{_scope}_client_email": audit.client.contact_email or "",
        f"a_{_scope}_client_phone": audit.client.contact_phone or "",
        f"a_{_scope}_client_addr":  audit.client.address or "",
    }
    for widget_key, value in queued.items():
        st.session_state[f"{_PENDING_PREFIX}{widget_key}"] = value

    # Collapse the Ariregister results panel after applying.
    st.session_state.pop(f"_co_search_client_{scope}", None)

    if rerun_scope:
        st.rerun(scope=rerun_scope)
    else:
        st.rerun()


def _apply_company_hit(hit) -> None:  # type: CompanyHit
    _apply_to_client({
        "name": hit.name,
        "reg_code": hit.reg_code,
        "address": hit.address,
    })


# (1) Unified picker — single combobox + Ariregister search button. Sits
# right under the Заказчик header so the auditor types name OR reg-code
# in one place; saved-client picks autofill via `autofill_from_picker`
# above; Ariregister hits fill all fields via `_apply_to_client`.
audit.client.name = client_picker(
    name_widget_key=k("client_name"),
    state_key_prefix=f"client_{scope}",
    suggestions=client_names(),
    current_name=audit.client.name,
    on_apply=_apply_company_hit,
) or ""

# (2) Sibling fields — auto-filled by `_apply_to_client` (Ariregister/
# Teatmik) and `autofill_from_picker` (saved-client pick).
col1, col2, col3 = st.columns(3)
with col1:
    audit.client.reg_code = st.text_input(
        "Reg. kood",
        value=audit.client.reg_code or "",
        key=k("client_reg"),
        help="Регистрационный код юр. лица заказчика (если есть). Для физ. лица оставить пустым.",
    ) or None
    hint_caption(reg_code_hint(audit.client.reg_code))
with col2:
    audit.client.contact_email = st.text_input(
        "E-mail", value=audit.client.contact_email or "", key=k("client_email")
    ) or None
with col3:
    audit.client.contact_phone = st.text_input(
        "Телефон", value=audit.client.contact_phone or "", key=k("client_phone")
    ) or None


def _apply_inads_to_client(hit) -> None:  # type: AddressHit
    audit.client.address = hit.address
    set_current(audit)
    # Seed the address text_input via the pending-widget queue so the
    # value shows up immediately on the next rerun (same pattern as the
    # other client fields above).
    st.session_state[f"{_PENDING_PREFIX}{k('client_addr')}"] = audit.client.address or ""
    st.session_state.pop(f"_addr_search_client_{scope}", None)
    st.session_state.pop(f"_addr_q_client_{scope}", None)
    st.rerun()


address_picker(
    key_prefix=f"client_{scope}",
    on_select=_apply_inads_to_client,
    label="🔎 Найти адрес заказчика в Maa-amet",
)

audit.client.address = st.text_input(
    "Адрес заказчика",
    value=audit.client.address or "",
    key=k("client_addr"),
    help=(
        "Адрес для переписки с заказчиком (может отличаться от адреса объекта). "
        "Можно набрать вручную или выбрать через поиск выше."
    ),
) or None
improve_button_for(
    text=audit.client.address or "",
    state_key_prefix=f"imp_client_addr_{scope}",
    section_ref=None,
    text_widget_key=k("client_addr"),
    apply=lambda v: setattr(audit.client, "address", v),
)

# Auto-save the draft now that the metadata + client form fields above
# have rendered and committed their values. As soon as the user types
# anything (purpose, client name, reg-code, etc.) audit.id is assigned —
# token-based features (Teatmik link, pending-imports) start working
# immediately, no manual «Save draft» click required.
ensure_draft_saved(audit)

# Optional fallback — the old Teatmik bookmarklet/userscript flow remains
# fully functional behind a feature flag (see «Подключения» page). Hidden
# inside a collapsed expander so it doesn't compete with Ariregister for
# attention but stays one click away if Ariregister ever fails.
if feature_flags.teatmik_enabled():
    with st.expander("🌐 Альтернативный источник: Teatmik (резерв)", expanded=False):
        # The unified picker stores its name/reg-code in `k("client_name")`
        # — re-use that as the Teatmik query so the auditor doesn't retype.
        _tk_query = (
            (st.session_state.get(k("client_name")) or "").strip()
            or (audit.client.reg_code or "").strip()
            or (audit.client.name or "").strip()
        )
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
                    "Введите название/рег-код заказчика в поле выше "
                    "(Ariregister) — ссылка на Teatmik активируется автоматически."
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
                mark_applied(imp.id)
                # Same path as the Ariregister picker — guarantees fields
                # appear in the form on the next rerun. `rerun_scope="app"`
                # because we're inside an @st.fragment.
                _apply_to_client(mapped, rerun_scope="app")
            if cr.button("❌ Отклонить", key=f"imp_client_reject_{imp.id}"):
                mark_rejected(imp.id)
                st.rerun(scope="app")


if feature_flags.teatmik_enabled():
    _render_pending_client_imports()

set_current(audit)
st.success(f"Текущий номер: **{audit.display_no()}** ({audit.type} / {audit.subtype})")
