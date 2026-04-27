"""Extract Building fields from an architectural project document.

Father's workflow today: he opens the project's *seletuskiri* (explanatory
note) in Word and copies whole chapters into the audit by hand. The extractor
short-circuits that — it takes plain text from the document (provided by
`tadf.intake.document_extract`) and asks Haiku 4.5 to populate a strict
JSON schema mirroring the Building model.

Hard rule: never invent values. Fields not stated in the document → null.
The UI shows a diff/preview so Fjodor explicitly accepts each field before
it touches `b.*`.
"""

from __future__ import annotations

from typing import Any

from tadf.external.cache import cache_get, cache_key, cache_put
from tadf.llm.client import MODEL_RANKER, complete_json

_NAMESPACE = "extract"
_TTL_DAYS = 30  # repeated uploads of the same doc reuse the result

# JSON schema mirrors src/tadf/models/building.py. All fields are nullable —
# the model leaves anything not stated in the source as None. We DO NOT use
# `minItems`/`maxItems` here — Anthropic's output_config rejects them on
# arrays (see src/tadf/llm/ranker.py L44 comment).
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "address": {"type": ["string", "null"]},
        "kataster_no": {"type": ["string", "null"]},
        "ehr_code": {"type": ["string", "null"]},
        "use_purpose": {"type": ["string", "null"]},
        "construction_year": {"type": ["integer", "null"]},
        "last_renovation_year": {"type": ["integer", "null"]},
        "designer": {"type": ["string", "null"]},
        "builder": {"type": ["string", "null"]},
        "footprint_m2": {"type": ["number", "null"]},
        "height_m": {"type": ["number", "null"]},
        "volume_m3": {"type": ["number", "null"]},
        "storeys_above": {"type": ["integer", "null"]},
        "storeys_below": {"type": ["integer", "null"]},
        # fire_class is normalised post-call (Anthropic rejects enum on
        # nullable/multi-type fields). Model is told by the system prompt
        # that only TP-1/TP-2/TP-3 are allowed; we re-validate below.
        "fire_class": {"type": ["string", "null"]},
        "site_area_m2": {"type": ["number", "null"]},
    },
    "required": [
        "address",
        "kataster_no",
        "ehr_code",
        "use_purpose",
        "construction_year",
        "last_renovation_year",
        "designer",
        "builder",
        "footprint_m2",
        "height_m",
        "volume_m3",
        "storeys_above",
        "storeys_below",
        "fire_class",
        "site_area_m2",
    ],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "Sa loed Eesti ehitusprojekti seletuskirja (architectural project's "
    "explanatory note). Sinu ülesanne — eraldada hoone metaandmed antud "
    "JSON-skeemi järgi.\n\n"
    "REEGLID:\n"
    "1. Kui väljaarvu pole tekstis SELGELT öeldud — jäta null. Ära arva, "
    "ära tuleta, ära järelda.\n"
    "2. Aasta — ainult `YYYY` (näide: 2018). Kui tekstis on '2018. a', "
    "tagasta 2018.\n"
    "3. Tulepüsivusklass — ainult üks väärtustest TP-1, TP-2, TP-3. "
    "Kõik muu — null.\n"
    "4. Mõõdud — ainult numbrid (m², m, m³). Ära lisa ühikuid.\n"
    "5. Kataster — formaadis XXXXX:XXX:XXXX (5+3+4 numbrit kooloniga). "
    "Kui formaat on muu — null.\n"
    "6. EHR-kood — ainult numbrid (7-12). Kui pole — null.\n"
    "7. Address peab sisaldama tänavat + numbrit + asulat.\n"
    "8. designer / builder — juriidilise isiku nimi (OÜ, AS, KÜ jms) "
    "kui see on selgelt mainitud projekti dokumendis kui projekteerija "
    "või ehitaja. Eraisikute nimesid ÄRA tagasta.\n\n"
    "Vasta AINULT JSON-objektiga, mis vastab antud skeemile. Ära lisa "
    "selgitusi, kommentaare, markdown-i."
)


def extract_building(text: str) -> dict[str, Any]:
    """Extract Building fields from the plain text of a project document.

    Returns a dict with all keys from `_SCHEMA["properties"]`; values that
    weren't stated in the document are `None`.

    Cached by `sha256(model + system + text[:5000])` so re-uploading the
    same document doesn't re-bill.
    """
    if not text or not text.strip():
        return {k: None for k in _SCHEMA["properties"]}

    # Cap context — most explanatory notes are well under 50k chars; longer
    # docs hint we should split, which is out of scope for this sprint.
    body = text[:50_000]

    key = cache_key(MODEL_RANKER, _SYSTEM_PROMPT, body[:5000])
    if (cached := cache_get(_NAMESPACE, key, ttl_days=_TTL_DAYS)) is not None:
        return cached["data"]

    user = (
        "Eralda hoone metaandmed järgmisest projekti seletuskirjast. "
        "Vasta JSON-objektiga skeemi järgi.\n\n"
        "--- DOKUMENT ---\n"
        f"{body}\n"
        "--- LÕPP ---"
    )

    data = complete_json(
        model=MODEL_RANKER,
        system=_SYSTEM_PROMPT,
        user=user,
        schema=_SCHEMA,
        max_tokens=1500,
    )

    # Defensive: ensure every schema key is present (with None if missing).
    out = {k: data.get(k) for k in _SCHEMA["properties"]}
    # Normalise fire_class — model sometimes returns "TP1" or lowercase.
    if isinstance(out.get("fire_class"), str):
        fc = out["fire_class"].upper().replace(" ", "").replace("TP", "TP-")
        if fc.startswith("TP--"):
            fc = "TP-" + fc[4:]
        out["fire_class"] = fc if fc in {"TP-1", "TP-2", "TP-3"} else None

    cache_put(_NAMESPACE, key, {"data": out})
    return out


# Helpful for the UI: which fields actually changed vs. current b.*.
def diff(current: dict[str, Any], extracted: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """Return [(field, current_value, proposed_value)] only where extracted
    is not None AND differs from current."""
    rows: list[tuple[str, Any, Any]] = []
    for k, proposed in extracted.items():
        if proposed is None:
            continue
        cur = current.get(k)
        # Skip floats that round to the same thing (avoid 100.0 vs 100 noise).
        if (
            isinstance(cur, float)
            and isinstance(proposed, (int, float))
            and abs(float(cur) - float(proposed)) < 1e-6
        ):
            continue
        if cur == proposed:
            continue
        rows.append((k, cur, proposed))
    return rows


__all__ = ["extract_building", "diff"]
