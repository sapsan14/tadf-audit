"""Legal-reference ranker.

Hard rule: the model RANKS existing references from `legal/references.yaml` —
it never invents new citations. We pass the candidate set explicitly and
constrain the output to that set via `enum`.
"""

from __future__ import annotations

from tadf.legal.loader import for_section
from tadf.llm.client import MODEL_RANKER, complete_json


def rank_legal_refs(observation: str, *, audit_type: str, section_ref: str) -> list[str]:
    """Return up to 3 legal-ref codes ranked by relevance.

    Candidate set comes from `for_section(section_ref)` — the audit_type
    filter is intentionally NOT passed in; section-keys filtering is enough,
    and the model is better at deciding type-relevance than our coarse table.

    The model picks from this candidate set only — `enum` JSON-schema
    constraint guarantees no hallucination.
    """
    candidates = for_section(section_ref.split(".", 1)[0])
    if not candidates:
        return []
    candidate_codes = [r.code for r in candidates]
    if len(candidate_codes) == 1:
        return candidate_codes  # only one option — skip the API call

    candidate_lines = "\n".join(f"- {r.code} — {r.title_et}" for r in candidates)

    system = (
        "Sa oled Eesti ehitusõiguse abiline. Sulle antakse audiitori "
        "märkus ning kandidaatide loend õigusviidetest. Vali kuni KOLM "
        "kõige asjakohasemat viidet pingerea järjekorras (kõige relevant­sem "
        "esimesena). VALI AINULT antud kandidaatide hulgast — ära mõtle välja "
        "uusi viiteid."
    )
    user = (
        f"Märkus:\n{observation.strip()}\n\nKandidaadid:\n{candidate_lines}\n\n"
        "Vasta JSON-objektiga, kus on väli 'codes' — ranked array of codes."
    )
    # NOTE: Anthropic's output_config JSON-schema rejects minItems/maxItems on
    # arrays. We enforce the 3-item cap in Python below instead.
    schema = {
        "type": "object",
        "properties": {
            "codes": {
                "type": "array",
                "items": {"type": "string", "enum": candidate_codes},
            },
        },
        "required": ["codes"],
        "additionalProperties": False,
    }
    user = user + "\nReturn at most 3 codes, ranked from most to least relevant."

    # Let API exceptions propagate — the caller (Наблюдения page) surfaces
    # errors via _record_error so the user sees what went wrong instead of
    # an empty result.
    data = complete_json(
        model=MODEL_RANKER,
        system=system,
        user=user,
        schema=schema,
        max_tokens=300,
    )
    raw = data.get("codes", [])
    # Defensive — ensure model didn't hallucinate; cap at 3
    return [c for c in raw if c in candidate_codes][:3]
