from __future__ import annotations

import pathlib
import sys

_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "src"))

from app._style import apply_consistent_layout  # noqa: E402

apply_consistent_layout()

from app._auth import require_login  # noqa: E402

require_login()

import streamlit as st  # noqa: E402

from tadf.legal.loader import all_references  # noqa: E402
from tadf.sections import SECTION_LABELS  # noqa: E402

st.title("📚 Правовая база")
st.caption(
    "Полный список правовых ссылок, доступных ИИ-ранжировщику и используемых в "
    "разделе 12 отчёта (Õiguslikud alused). Если нужного акта здесь нет — добавьте "
    "его в `src/tadf/legal/references.yaml` и перезапустите приложение."
)

refs = all_references()


# Group by category for browsability
def _category(code: str) -> str:
    if code.startswith("EhS "):
        return "Ehitusseadustik (EhS)"
    if code.startswith("EhSRS"):
        return "EhSRS — Ehitusseadustiku rakendamise seadus"
    if "MTR" in code or "auditi tegemise" in code or "Ehitise dokumendid" in code or "ehitusprojektile" in code or "esitamise kord" in code:
        return "MTR määrused (министерские постановления)"
    if "Tuleohutuse" in code:
        return "Tuleohutuse seadus"
    if code.startswith("EVS 812"):
        return "EVS 812 — Ehitiste tuleohutus"
    if code.startswith("EVS-EN") or code.startswith("EVS 932") or code.startswith("ET-2"):
        return "EVS / EVS-EN — Eurokoodeksid и стандарты"
    if "Korteriomandi" in code:
        return "Прочие законы"
    return "Прочее"


by_cat: dict[str, list] = {}
for r in refs:
    by_cat.setdefault(_category(r.code), []).append(r)

# Search box on top
search = st.text_input(
    "🔎 Поиск (по коду или названию)",
    placeholder="например: EVS 812, EhS, tuleohutus…",
    key="legal_search",
)


def _matches(r, q: str) -> bool:
    if not q:
        return True
    q = q.lower()
    return q in r.code.lower() or q in r.title_et.lower()


total_shown = 0
for category, items in by_cat.items():
    visible = [r for r in items if _matches(r, search)]
    if not visible:
        continue
    total_shown += len(visible)
    with st.expander(f"**{category}** ({len(visible)})", expanded=bool(search)):
        for r in visible:
            cols = st.columns([2, 5, 3])
            with cols[0]:
                st.markdown(f"**`{r.code}`**")
            with cols[1]:
                st.write(r.title_et)
                if r.url:
                    st.markdown(f"[🔗 riigiteataja.ee]({r.url})")
            with cols[2]:
                if r.section_keys:
                    sec_labels = ", ".join(
                        f"{k} {SECTION_LABELS.get(k, '').split('.', 1)[-1].strip()[:30]}"
                        if k in SECTION_LABELS
                        else k
                        for k in r.section_keys
                    )
                    st.caption(f"Применимо к: {sec_labels}")
                else:
                    st.caption("Применимо везде")
                if r.audit_types:
                    st.caption(f"Типы аудита: {', '.join(r.audit_types)}")

if search and total_shown == 0:
    st.info("Ничего не найдено. Попробуйте другой запрос.")

st.divider()
st.caption(
    f"Всего записей: **{len(refs)}** · показано: **{total_shown if search else len(refs)}**.  \n"
    "Каждая запись — одна правовая ссылка, доступная ИИ-ранжировщику в разделе «Находки»."
)
