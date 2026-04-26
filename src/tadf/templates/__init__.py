from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent
BOILERPLATE_PATH = TEMPLATES_DIR / "boilerplate.yaml"


def template_for(subtype: str) -> Path:
    """Return the docxtpl master for the given audit subtype.

    Falls back to `kasutuseelne` if the requested subtype's template doesn't
    exist (e.g. user added a new subtype not yet generated).
    """
    candidate = TEMPLATES_DIR / f"ea_{subtype}.docx"
    if candidate.exists():
        return candidate
    return TEMPLATES_DIR / "ea_kasutuseelne.docx"


# Back-compat alias used by tests / older callers
EA_KASUTUSEELNE = TEMPLATES_DIR / "ea_kasutuseelne.docx"
