"""Photo captioner — image + brief auditor note -> Estonian caption + section_ref.

Uses Claude Haiku 4.5 (vision-capable, fast). Returns structured JSON:
{ "caption": "...", "section_ref": "6.1" }
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from tadf.llm.client import MODEL_CAPTION
from tadf.llm.client import complete_with_image as _complete_with_image
from tadf.sections import SECTION_KEYS, SECTION_LABELS

SYSTEM_PROMPT = """\
Sa oled ehitusjärelevalve assistent. Vaata pilti ja koosta:
1. Lühike (kuni 12 sõna) eestikeelne pildiallkiri, mis kirjeldab täpselt seda, \
mida fotol näha on (komponent, materjal, seisukord). Ära kirjelda fotot \
("vaade...", "Foto näitab...") — kirjelda OBJEKTI.
2. Soovita kõige sobivam jaotise number ehitise auditi aruandes \
(nt "6.1" vundamendile, "8.7" suitsueemaldusele, "16" üldkogumile fotodest).

Vasta AINULT JSON-formaadis kahe väljaga: caption ja section_ref.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string", "description": "Estonian caption, ≤12 words"},
        "section_ref": {
            "type": "string",
            "enum": SECTION_KEYS,
            "description": "Suggested section reference",
        },
    },
    "required": ["caption", "section_ref"],
    "additionalProperties": False,
}


def caption_photo(image_path: str | Path, auditor_note: str = "") -> dict:
    """Return {caption, section_ref} for the given photo."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(image_path)

    media_type, _ = mimetypes.guess_type(str(path))
    if not media_type or not media_type.startswith("image/"):
        raise ValueError(f"Not an image: {path}")

    image_bytes = path.read_bytes()
    user_text = (
        "Audiitori märkus: " + (auditor_note.strip() or "(märkus puudub)")
        + "\n\nKoostage allkiri ja soovitatud jaotis (vasta JSON-iga)."
    )

    # Vision endpoint doesn't yet expose output_config in the SDK we use, so we
    # do a free-form vision call and parse the JSON ourselves.
    raw = _complete_with_image(
        model=MODEL_CAPTION,
        system=SYSTEM_PROMPT,
        image_bytes=image_bytes,
        image_media_type=media_type,
        user_text=user_text,
        max_tokens=200,
    )
    return _parse_json_or_default(raw)


def _parse_json_or_default(raw: str) -> dict:
    """Tolerant JSON parser — Haiku occasionally wraps JSON in prose."""
    import json
    import re

    # Try direct parse first
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Find first {...} block in the response
        m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if not m:
            return {"caption": raw[:80].strip(), "section_ref": "16"}
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"caption": raw[:80].strip(), "section_ref": "16"}

    caption = str(data.get("caption", "")).strip() or "(нет описания)"
    section = str(data.get("section_ref", "16")).strip()
    if section not in SECTION_LABELS:
        section = "16"
    return {"caption": caption, "section_ref": section}
