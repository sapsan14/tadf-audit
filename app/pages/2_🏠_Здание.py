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
st.caption("Если данные неизвестны (особенно для pre-2003 зданий) — оставьте пустым.")
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
with col2:
    b.builder = st.text_input(
        "Builder (ehitaja)",
        value=b.builder or "",
        key=k("builder"),
        help="Кто строил здание (генподрядчик).",
    ) or None

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

audit.building = b
set_current(audit)
