from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

import streamlit as st  # noqa: E402

from app._state import get_current, set_current  # noqa: E402
from app._widgets import flush_improve_pending, improve_button_for  # noqa: E402
from tadf.api.imports import (  # noqa: E402
    list_pending,
    map_teatmik,
    mark_applied,
    mark_rejected,
)
from tadf.api.tokens import issue as _issue_token  # noqa: E402
from tadf.external.ehr_client import lookup_ehr  # noqa: E402
from tadf.external.links import teatmik_company_url  # noqa: E402
from tadf.intake.document_extract import extract_from_upload  # noqa: E402
from tadf.llm import is_available as llm_available  # noqa: E402
from tadf.llm.extractor import diff as _extract_diff  # noqa: E402


def _with_token_fragment(url: str, audit_id: int, *, target: str | None = None) -> str:
    """Append `#tadf=<token>[&target=<slot>]` to a URL so the in-browser
    helper can read both the auth token and which TADF form section the
    auditor was on (so we can default the import target without showing
    a picker)."""
    token = _issue_token(audit_id)
    sep = "&" if "#" in url else "#"
    extra = f"&target={target}" if target else ""
    return f"{url}{sep}tadf={token}{extra}"


def _coerce_for_building_field(field_name: str, value):
    """Coerce extractor output to the Pydantic-declared type for that field.

    Pydantic v2 doesn't validate on plain `setattr` (no `validate_assignment`),
    so an int slipping into a `float | None` field reaches `st.number_input`
    as int and trips StreamlitMixedNumericTypesError when the widget's
    min_value/step are floats. Coerce here so both `b.field` and
    `st.session_state[widget_key]` carry the right type.
    """
    if value is None:
        return None
    from typing import get_args

    from tadf.models import Building as _B

    info = _B.model_fields.get(field_name)
    if info is None:
        return value
    args = [a for a in get_args(info.annotation) if a is not type(None)]
    target = args[0] if len(args) == 1 else info.annotation
    if target is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if target is int and isinstance(value, float) and value.is_integer():
        return int(value)
    return value

flush_improve_pending()

st.title("Здание (auditi objekt)")

audit = get_current()
b = audit.building

# Scope widget state per-audit so reloading a different audit reseeds the form,
# and use explicit keys so +/- steppers persist across reruns.
scope = audit.id or "new"


def k(name: str) -> str:
    return f"b_{scope}_{name}"


# ---------------------------------------------------------------------------
# Pending-slot application (avoids Streamlit widget-state bug — see commit
# e48387c). When the user clicks "Применить" on the extractor preview, we
# stash the chosen fields here and rerun; this block applies them BEFORE
# any widget renders, so we can also safely pop the widget keys to force
# them to reseed from the new b.* values.
# ---------------------------------------------------------------------------
_PENDING_KEY = f"_pending_b_{scope}"
if _PENDING_KEY in st.session_state:
    pending = st.session_state.pop(_PENDING_KEY)
    for field, value in pending.items():
        coerced = _coerce_for_building_field(field, value)
        if hasattr(b, field):
            setattr(b, field, coerced)
        # Bulletproof reseed of the widget state. We're at the very top
        # of the script — no widgets instantiated yet — so writing the
        # widget's session_state key is allowed (Streamlit only forbids
        # post-instantiation writes). Pop'ing alone has been observed to
        # leave number_input stuck on the old display value; setting the
        # session_state value directly forces the widget to render the
        # new value on this run.
        widget_key = k(field)
        if coerced is None:
            st.session_state.pop(widget_key, None)
        else:
            st.session_state[widget_key] = coerced
    audit.building = b
    set_current(audit)


# ---------------------------------------------------------------------------
# 📥 Pending imports from the Teatmik bookmarklet / Tampermonkey userscript.
# (EHR no longer goes through here — we hit the public ehr.ee API directly
# from Hetzner via tadf.external.ehr_client.lookup_ehr; see the dedicated
# "Подгрузить из EHR" button below the EHR-code field.)
# ---------------------------------------------------------------------------
if audit.id is not None:
    _imports = list_pending(audit.id)
    for imp in _imports:
        if imp.kind == "teatmik":
            # target=client imports surface on the Новый аудит page where
            # the client form lives; here we handle designer / builder /
            # no-hint imports.
            if imp.payload.get("target") == "client":
                continue
            mapped = map_teatmik(imp.payload)
            # The browser helper passes `target` based on which TADF form
            # section the auditor was on (designer / builder / client).
            # We default the picker to the hint and pre-fill the entire
            # contact bundle on apply when target=client.
            hinted_target = mapped.pop("target", None)
            with st.container(border=True):
                st.markdown(
                    f"📥 **Импорт из Teatmik** — получено "
                    f"{imp.received_at.strftime('%H:%M:%S')}"
                    + (f" → **{hinted_target}**" if hinted_target else "")
                )
                if imp.source_url:
                    st.caption(f"Источник: {imp.source_url}")
                if not mapped:
                    st.warning("Пустая карточка компании (нет полезных полей).")
                else:
                    st.write("Найдено:")
                    for kfield, val in mapped.items():
                        st.write(f"- `{kfield}`: {val}")

                target_options = ["designer", "builder", "client"]
                default_target = (
                    hinted_target if hinted_target in target_options else "designer"
                )
                tc1, tc2, _tc3, tc4 = st.columns(4)
                target = tc1.selectbox(
                    "Куда вставить",
                    options=target_options,
                    index=target_options.index(default_target),
                    key=f"imp_tm_target_{imp.id}",
                    label_visibility="collapsed",
                )
                if tc2.button("✅ Применить", type="primary", key=f"imp_tm_apply_{imp.id}"):
                    name = mapped.get("name") or mapped.get("reg_code")
                    if target == "designer":
                        st.session_state[_PENDING_KEY] = {"designer": name}
                    elif target == "builder":
                        st.session_state[_PENDING_KEY] = {"builder": name}
                    elif target == "client":
                        if audit.client is None:
                            from tadf.models import Client

                            audit.client = Client(name=name or "")
                        else:
                            audit.client.name = name or ""
                        if mapped.get("reg_code"):
                            audit.client.reg_code = mapped["reg_code"]
                        if mapped.get("address"):
                            audit.client.address = mapped["address"]
                        if mapped.get("email"):
                            audit.client.contact_email = mapped["email"]
                        if mapped.get("phone"):
                            audit.client.contact_phone = mapped["phone"]
                        set_current(audit)
                    mark_applied(imp.id)
                    st.rerun()
                if tc4.button("❌ Отклонить", key=f"imp_tm_reject_{imp.id}"):
                    mark_rejected(imp.id)
                    st.rerun()


# ---------------------------------------------------------------------------
# 📄 Импорт из проекта — upload a project explanatory note (DOCX/PDF) and
# let Claude extract building fields. Only fields the user explicitly
# accepts are written to b.*.
# ---------------------------------------------------------------------------
_EXTRACT_KEY = f"_extract_result_{scope}"
_EXTRACT_RAW_KEY = f"_extract_raw_{scope}"

with st.expander("📄 Импорт из проекта (тезисы из seletuskiri)", expanded=False):
    if not llm_available():
        st.info(
            "🤖 ИИ-извлечение выключено — нет ключа Anthropic. Заполните "
            "поля вручную или настройте ANTHROPIC_API_KEY."
        )
    else:
        st.caption(
            "Загрузите DOCX/PDF архитектурного проекта (пояснительная записка / "
            "*seletuskiri*). Claude (Haiku 4.5) попытается извлечь поля здания. "
            "Каждое поле показывается в превью с галочкой — применяются только "
            "выбранные."
        )
        uploaded = st.file_uploader(
            "Файл проекта",
            type=["docx", "pdf"],
            accept_multiple_files=False,
            key=f"extract_upload_{scope}",
        )
        run_clicked = st.button(
            "🤖 Извлечь данные",
            type="primary",
            disabled=uploaded is None,
            key=f"extract_run_{scope}",
        )
        if run_clicked and uploaded is not None:
            with st.status("Claude (Haiku 4.5) читает документ…", expanded=True) as status:
                try:
                    extracted, raw_text = extract_from_upload(uploaded)
                    st.session_state[_EXTRACT_KEY] = extracted
                    st.session_state[_EXTRACT_RAW_KEY] = raw_text
                    status.update(label="Готово ✅", state="complete", expanded=False)
                except Exception as e:  # noqa: BLE001
                    status.update(label="Ошибка ❌", state="error", expanded=True)
                    st.error(f"Не удалось извлечь данные: {type(e).__name__}: {e}")
            st.rerun()

        # ---- Preview / diff panel ----
        if _EXTRACT_KEY in st.session_state:
            extracted = st.session_state[_EXTRACT_KEY]
            current = b.model_dump()
            rows = _extract_diff(current, extracted)
            if not rows:
                st.success(
                    "✅ Все извлечённые поля совпадают с уже введёнными — "
                    "применять нечего."
                )
                if st.button("OK", key=f"extract_ok_{scope}"):
                    del st.session_state[_EXTRACT_KEY]
                    st.session_state.pop(_EXTRACT_RAW_KEY, None)
                    st.rerun()
            else:
                st.markdown(f"**Извлечено {len(rows)} поле(ей).** Снимите галочки, если что-то не то:")
                accept: dict[str, bool] = {}
                # Header row
                hc1, hc2, hc3, hc4 = st.columns([2, 3, 3, 1])
                hc1.markdown("**Поле**")
                hc2.markdown("**Сейчас**")
                hc3.markdown("**Извлечено**")
                hc4.markdown("**✅**")
                for field, cur, proposed in rows:
                    rc1, rc2, rc3, rc4 = st.columns([2, 3, 3, 1])
                    rc1.write(f"`{field}`")
                    rc2.write("(пусто)" if cur in (None, "") else str(cur))
                    rc3.write(str(proposed))
                    accept[field] = rc4.checkbox(
                        "",
                        value=True,
                        key=f"extract_accept_{scope}_{field}",
                        label_visibility="collapsed",
                    )
                ac1, ac2, _ = st.columns([2, 2, 4])
                if ac1.button(
                    "✅ Применить выбранные",
                    type="primary",
                    key=f"extract_apply_{scope}",
                ):
                    chosen = {field: extracted[field] for field, ok in accept.items() if ok}
                    st.session_state[_PENDING_KEY] = chosen
                    del st.session_state[_EXTRACT_KEY]
                    st.session_state.pop(_EXTRACT_RAW_KEY, None)
                    for field in chosen:
                        st.session_state.pop(f"extract_accept_{scope}_{field}", None)
                    st.rerun()
                if ac2.button("❌ Отклонить всё", key=f"extract_reject_{scope}"):
                    del st.session_state[_EXTRACT_KEY]
                    st.session_state.pop(_EXTRACT_RAW_KEY, None)
                    for field, _, _ in rows:
                        st.session_state.pop(f"extract_accept_{scope}_{field}", None)
                    st.rerun()
                # Debug — what Claude actually saw
                if _EXTRACT_RAW_KEY in st.session_state:
                    with st.expander("🔍 Что увидел Claude (debug)", expanded=False):
                        raw = st.session_state[_EXTRACT_RAW_KEY]
                        st.caption(f"Длина текста: {len(raw)} символов")
                        st.text(raw[:5000] + ("…" if len(raw) > 5000 else ""))


b.address = st.text_input(
    "Адрес объекта (Aadress)",
    value=b.address,
    key=k("address"),
    help=(
        "Полный почтовый адрес здания в формате «улица номер, населённый пункт, "
        "уезд». Например: «Auga tn 8, Narva-Jõesuu linn, Ida-Viru maakond»."
    ),
)

col1, col2 = st.columns(2)
with col1:
    b.kataster_no = (
        st.text_input(
            "Katastritunnus",
            value=b.kataster_no or "",
            help=(
                "Кадастровый номер кинниста в формате «XXXXX:XXX:XXXX» "
                "(например 85101:004:0020). Можно посмотреть на geoportaal.maaamet.ee. "
                "По §5 — обязательно либо это, либо EHR-код."
            ),
            key=k("kataster_no"),
        )
        or None
    )
with col2:
    b.ehr_code = (
        st.text_input(
            "Ehitisregistri kood (EHR)",
            value=b.ehr_code or "",
            help=(
                "Код здания в Ehitisregister (7–12 цифр). Найти можно на "
                "ehr.ee по адресу. Если здание не зарегистрировано — оставьте "
                "пусто, тогда обязателен kataster_no."
            ),
            key=k("ehr_code"),
        )
        or None
    )

# EHR direct lookup — uses the public e-ehitus API
# (livekluster.ehr.ee/api/building/v3/buildingData?ehr_code=…) which
# requires no auth. One click → all fields populated. The preview/diff
# pattern reuses the same _PENDING_KEY apply machinery as the project-
# doc extractor so we never write to widgets after they've rendered.
_EHR_RESULT_KEY = f"_ehr_result_{scope}"

lc1, lc2, lc3, _ = st.columns([3, 2, 2, 3])
ehr_pull = lc1.button(
    "🔎 Подгрузить из EHR",
    type="primary",
    disabled=not (b.ehr_code or "").strip(),
    key=f"ehr_pull_{scope}",
    use_container_width=True,
    help=(
        "Идёт прямо на livekluster.ehr.ee/api — без логина, без браузера. "
        "Кешируется на 30 дней; кнопка ниже принудительно обновляет."
        if (b.ehr_code or "").strip()
        else "Введите EHR-код выше, чтобы включить."
    ),
)
ehr_refresh = lc2.button(
    "🔄 Свежие из EHR",
    disabled=not (b.ehr_code or "").strip(),
    key=f"ehr_refresh_{scope}",
    use_container_width=True,
    help=(
        "Бьёт мимо локального кеша, хочет актуальные данные с live-сервера. "
        "Используй, если знаешь, что в EHR что-то изменилось (новый "
        "энергомаркер, обновление адреса, etc)."
    ),
)
if b.kataster_no:
    # X-GIS Maa-info opens the kataster directly on the map. The geoportaal
    # Kinnistu-otsing form variant requires the user to click "Otsi" first,
    # which is annoying; this URL skips that step.
    lc3.link_button(
        "🗺️ Maa-amet",
        f"https://xgis.maaamet.ee/xgis2/page/app/maainfo?ku={b.kataster_no}",
        use_container_width=True,
        help="Открывает кадастр на интерактивной карте Maa-amet.",
    )
else:
    lc2.button(
        "🗺️ Maa-amet (по кадастру)",
        disabled=True,
        key=f"maaamet_disabled_{scope}",
        help="Введите кадастровый номер слева — ссылка на geoportaal.maaamet.ee активируется.",
        use_container_width=True,
    )

if ehr_pull or ehr_refresh:
    with st.status("Тяну из EHR (livekluster.ehr.ee)…", expanded=True) as status:
        result = lookup_ehr(b.ehr_code, force_refresh=ehr_refresh)
        if result:
            st.session_state[_EHR_RESULT_KEY] = result
            status.update(
                label="Готово ✅" + (" (свежие, без кеша)" if ehr_refresh else ""),
                state="complete",
                expanded=False,
            )
        else:
            status.update(label="Не нашёл такого здания в EHR ❌", state="error")
    st.rerun()

if _EHR_RESULT_KEY in st.session_state:
    ehr_data = st.session_state[_EHR_RESULT_KEY]
    current = b.model_dump()
    rows = _extract_diff(current, ehr_data)
    with st.container(border=True):
        st.markdown(f"📥 **Импорт из EHR** — полей: **{len(rows)}**")
        if not rows:
            st.success("Все поля совпадают с уже введёнными — нечего применять.")
            if st.button("OK", key=f"ehr_ok_{scope}"):
                del st.session_state[_EHR_RESULT_KEY]
                st.rerun()
        else:
            hc1, hc2, hc3, hc4 = st.columns([2, 3, 3, 1])
            hc1.markdown("**Поле**")
            hc2.markdown("**Сейчас**")
            hc3.markdown("**Из EHR**")
            hc4.markdown("**✅**")
            accept_ehr: dict[str, bool] = {}
            for field, cur, proposed in rows:
                rc1, rc2, rc3, rc4 = st.columns([2, 3, 3, 1])
                rc1.write(f"`{field}`")
                rc2.write("(пусто)" if cur in (None, "") else str(cur))
                rc3.write(str(proposed))
                accept_ehr[field] = rc4.checkbox(
                    "",
                    value=True,
                    key=f"ehr_accept_{scope}_{field}",
                    label_visibility="collapsed",
                )
            ac1, ac2, _ = st.columns([2, 2, 4])
            if ac1.button("✅ Применить выбранные", type="primary", key=f"ehr_apply_{scope}"):
                chosen = {f: ehr_data[f] for f, ok in accept_ehr.items() if ok and f in ehr_data}
                st.session_state[_PENDING_KEY] = chosen
                del st.session_state[_EHR_RESULT_KEY]
                for f, _, _ in rows:
                    st.session_state.pop(f"ehr_accept_{scope}_{f}", None)
                st.rerun()
            if ac2.button("❌ Отклонить всё", key=f"ehr_reject_{scope}"):
                del st.session_state[_EHR_RESULT_KEY]
                for f, _, _ in rows:
                    st.session_state.pop(f"ehr_accept_{scope}_{f}", None)
                st.rerun()
        with st.expander("🔍 Что вернул EHR (debug)", expanded=False):
            st.json(ehr_data)

b.use_purpose = st.text_input(
    "Kasutusotstarve (назначение)",
    value=b.use_purpose or "",
    key=k("use_purpose"),
    help=(
        "Назначение здания по EHR-классификации. Стандартные значения: "
        "aiamaja, üksikelamu, korterelamu, ärihoone, tööstushoone, "
        "majandushoone. Полный список — на ehr.ee."
    ),
) or None

col1, col2, col3 = st.columns(3)
with col1:
    b.construction_year = st.number_input(
        "Год постройки",
        min_value=1800,
        max_value=2100,
        value=b.construction_year or 2000,
        step=1,
        key=k("construction_year"),
        help=(
            "Год сдачи здания в эксплуатацию. Если оригинальные документы "
            "утеряны и год точно неизвестен — поставьте приближённую оценку "
            "и обязательно отметьте «Pre-2003 ehitis» + заполните пояснение "
            "в substitute_docs_note ниже."
        ),
    )
with col2:
    _last = st.number_input(
        "Год последней реконструкции (0 = не было)",
        min_value=0,
        max_value=2100,
        value=b.last_renovation_year or 0,
        step=1,
        key=k("last_renovation_year"),
        help=(
            "Год последней значительной реконструкции (если была). 0 означает "
            "«реконструкции не было». Влияет на то, какие нормы применимы — "
            "после реконструкции применяются новые требования."
        ),
    )
    b.last_renovation_year = _last if _last > 0 else None
with col3:
    b.pre_2003 = st.checkbox(
        "Pre-2003 ehitis",
        value=b.pre_2003,
        help=(
            "Здание построено ДО 2003 года, когда вступил в силу Ehitusseadustik. "
            "По EhSRS § 28 — для таких зданий аудит ЗАМЕНЯЕТ отсутствующую "
            "ehitusprojekti документацию. Если включено, обязательно заполните "
            "поле substitute_docs_note внизу страницы."
        ),
        key=k("pre_2003"),
    )

st.subheader("Технические показатели (для §10 отчёта)")
st.caption(
    "Все значения по правилам RT 110062015008 «Ehitise tehniliste andmete "
    "loetelu». Замеры — по фактическим обмерам или по проектной документации."
)
col1, col2, col3 = st.columns(3)
with col1:
    _fp = st.number_input(
        "Ehitisealune pind (m²)",
        min_value=0.0,
        value=b.footprint_m2 or 0.0,
        step=0.5,
        format="%.1f",
        key=k("footprint_m2"),
        help=(
            "Площадь застройки — площадь горизонтальной проекции здания на "
            "землю, по внешнему контуру стен. По §5 + RT 110062015008 — "
            "обязательное поле."
        ),
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
        help="Высота здания от уровня земли до верхней точки крыши (по карнизу).",
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
        help=(
            "Строительный объём здания — объём по внешним размерам, "
            "включая чердак и подвал. По RT 110062015008."
        ),
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
        help="Maapealsete korruste arv — этажи, центр пола которых выше уровня земли.",
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
        help="Maa-aluste korruste arv — подвальные этажи (0 = подвала нет).",
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
        help=(
            "Площадь земельного участка (кинниста), на котором стоит здание. "
            "Берётся из кадастровых данных (geoportaal.maaamet.ee)."
        ),
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
    help=(
        "Класс огнестойкости здания по EVS 812-7 / Tuleohutuse seadus:\n"
        "• TP-1 — высокий (R 60+, для зданий выше 3 этажей или массового "
        "пребывания людей)\n"
        "• TP-2 — средний (R 30, для большинства многоквартирных)\n"
        "• TP-3 — низкий (R 15, для üksikelamu, aiamaja, garaaž)\n\n"
        "Если класс указан, в разделе 8 отчёта обязательно должна быть хотя "
        "бы одно наблюдение по пожарной безопасности — иначе не пройдёт §5 "
        "проверку."
    ),
)

st.subheader("Проектировщик / строитель")
st.caption(
    "Если данные неизвестны (особенно для pre-2003 зданий) — оставьте пустым. "
    "Ссылка «🔎 Teatmik» открывает реестр предприятий в новой вкладке "
    "(там можно проверить рег-код, адрес и статус)."
)
col1, col2 = st.columns(2)
with col1:
    b.designer = st.text_input(
        "Designer (projekteerija)",
        value=b.designer or "",
        key=k("designer"),
        help=(
            "Кто проектировал здание (физ. лицо или фирма). "
            "Берётся из ehitusprojekti документации, если есть."
        ),
    ) or None
    _designer_link = teatmik_company_url(b.designer) if b.designer else None
    if _designer_link:
        if audit.id is not None:
            _designer_link = _with_token_fragment(_designer_link, audit.id, target="designer")
        st.link_button("🔎 Teatmik (designer)", _designer_link, use_container_width=True)
    else:
        st.button(
            "🔎 Teatmik (designer)",
            disabled=True,
            key=f"teatmik_designer_disabled_{scope}",
            help="Введите имя проектировщика выше — ссылка на Teatmik активируется.",
            use_container_width=True,
        )
with col2:
    b.builder = st.text_input(
        "Builder (ehitaja)",
        value=b.builder or "",
        key=k("builder"),
        help="Кто строил здание (генподрядчик).",
    ) or None
    _builder_link = teatmik_company_url(b.builder) if b.builder else None
    if _builder_link:
        if audit.id is not None:
            _builder_link = _with_token_fragment(_builder_link, audit.id, target="builder")
        st.link_button("🔎 Teatmik (builder)", _builder_link, use_container_width=True)
    else:
        st.button(
            "🔎 Teatmik (builder)",
            disabled=True,
            key=f"teatmik_builder_disabled_{scope}",
            help="Введите имя строителя выше — ссылка на Teatmik активируется.",
            use_container_width=True,
        )

if b.pre_2003:
    b.substitute_docs_note = st.text_area(
        "Substitute-docs note (EhSRS § 28)",
        value=b.substitute_docs_note or "",
        help=(
            "По EhSRS § 28 — для зданий, построенных до 2003 г., аудит "
            "ЗАМЕНЯЕТ отсутствующую ehitusprojekti документацию. Опишите, "
            "какие документы отсутствуют (например «оригинальный проект "
            "утерян»; «нет акта сдачи-приёмки») и каким образом этот аудит "
            "их заменяет — это нужно для регистрации в Ehitisregister."
        ),
        key=k("substitute_docs_note"),
    ) or None
    improve_button_for(
        text=b.substitute_docs_note or "",
        state_key_prefix=f"imp_subst_docs_{scope}",
        section_ref="2",
        text_widget_key=k("substitute_docs_note"),
        apply=lambda v: setattr(b, "substitute_docs_note", v),
    )

audit.building = b
set_current(audit)
