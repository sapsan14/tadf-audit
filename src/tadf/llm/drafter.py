"""Narrative drafter — auditor's bullet observations -> formal Estonian prose.

Hard rule: refuses to draft for sections 11 (Kokkuvõte) and 14 (Lõpphinnang) —
those are auditor-only by both legal convention and the project's signed-off
plan. Anything that reaches those sections is the auditor's own writing.
"""

from __future__ import annotations

from tadf.llm.client import MODEL_DRAFTER, complete_text
from tadf.sections import SECTION_LABELS

# Sections where the auditor must write — no LLM drafting, no LLM polish.
LOCKED_SECTIONS = {"11", "14"}


def is_locked(section_ref: str) -> bool:
    return section_ref.split(".", 1)[0] in LOCKED_SECTIONS


SYSTEM_PROMPT = """\
Sa oled Eesti ehitusjärelevalve assistent. Su ainus ülesanne on muuta inseneri \
lühikesed märkused (tavaliselt vene või eesti keeles, sageli konspektidena) \
formaalse eesti keele lõikudeks, mis sobivad ehitise auditi aruandesse.

Reeglid:
1. Kasuta ainult eesti keelt. Kui sisendis on venekeelseid sõnu või termineid, \
tõlgi need kontekstipõhiselt eesti tehnikatermineiks.
2. Säilita kõik faktid täpselt nagu inseneril. Ära lisa uusi mõõdikuid, \
arvandmeid ega oletusi, mida sisendis ei olnud.
3. Kasuta passiivset, neutraalset, formaalset registrit ("paigaldatud", \
"tuvastatud", "vastab nõuetele"). Väldi esimese ja teise isiku vorme.
4. Kirjuta üks lõik (1–4 lauset) — mitte loendit, kui sisend pole otseselt \
loendamise kohta.
5. Kasuta jaotisele tüüpilist sõnavara — vundament, välisseinad, \
tehnosüsteemid, tulepüsivusklass, evakuatsiooniteed jne.
6. Kui sisend on liiga ebamäärane, et sellest formaalset lõiku teha, \
vasta täpselt: "[ВВОД СЛИШКОМ КРАТКИЙ — добавьте больше деталей]" — ÄRA \
mõtle välja täiendavaid fakte.

Vasta AINULT lõpliku lõigu tekstiga. Ei mingit selgitust, ei mingit \
lisajuttu, ei mingit "Vastus:" prefiksit.
"""


def draft_narrative(section_ref: str, bullets: str) -> str:
    """Expand bullet observations into a formal Estonian paragraph."""
    if is_locked(section_ref):
        raise ValueError(
            f"Section {section_ref} is auditor-only — narrative drafting is disabled."
        )

    bullets = bullets.strip()
    if not bullets:
        raise ValueError("Empty bullets — nothing to draft.")

    section_label = SECTION_LABELS.get(section_ref, section_ref)
    user = f"Jaotis: {section_label}\n\nInseneri märkused:\n{bullets}"
    return complete_text(
        model=MODEL_DRAFTER,
        system=SYSTEM_PROMPT,
        user=user,
        max_tokens=800,
    )
