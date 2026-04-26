"""Estonian polish — clean grammar/style/terminology of auditor-written text.

Conservative: never changes facts, never adds content, only fixes grammar,
terminology consistency, and formal register. Returns either the polished
text OR the original text unchanged if no improvements are needed.

Hard rule: refuses to polish sections 11 and 14 — same auditor-only lock as
the drafter.
"""

from __future__ import annotations

from tadf.llm.client import MODEL_POLISH, complete_text
from tadf.llm.drafter import is_locked

SYSTEM_PROMPT = """\
Sa oled eesti keele toimetaja, kes parandab ainult ehitise auditi aruande \
teksti grammatikat, terminoloogiat ja formaalset registrit. Sa EI muuda \
ega lisa ühtki fakti — kõik arvud, mõõdud, materjalid, hinnangud ja \
järeldused jäävad nii nagu on.

Mida võid muuta:
- Grammatilised vead (käände-, vormi-, kongruentsi vead)
- Mitteformaalsed väljendid -> formaalseks (nt "natuke" -> "veidi")
- Sõna­korduste vältimine sünonüümidega
- Kohmakad konstruktsioonid -> sujuvamad
- Terminoloogia ühtlustamine ehitusvaldkonna standardile (EVS-id)

Mida sa EI muuda:
- Faktid, arvud, mõõdud
- Tehnilised hinnangud (rahuldav / mitterahuldav / hea / ohtlik)
- Lõikude ülesehitus / järjestus
- Materjalide nimetused
- Õigusviited

Kui tekst on juba korras (ei vaja parandusi) — vasta täpselt: \
"[NO_CHANGES_NEEDED]"

Vasta AINULT redigeeritud tekstiga (ilma selgituste, eessõnata).\
"""


def polish_text(text: str, *, section_ref: str | None = None) -> str:
    """Return the polished version of `text`. If no changes are needed,
    returns the original text unchanged."""
    if section_ref and is_locked(section_ref):
        raise ValueError(
            f"Section {section_ref} is auditor-only — polish is disabled."
        )

    text = text.strip()
    if not text:
        return text

    polished = complete_text(
        model=MODEL_POLISH,
        system=SYSTEM_PROMPT,
        user=text,
        max_tokens=max(800, len(text) // 2),
    )
    if polished.strip() == "[NO_CHANGES_NEEDED]":
        return text
    return polished or text
