"""Load legal references from the YAML seed."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from tadf.models import LegalReference

REFERENCES_PATH = Path(__file__).parent / "references.yaml"


@lru_cache(maxsize=1)
def load_references(path: Path | None = None) -> list[LegalReference]:
    src = path or REFERENCES_PATH
    raw = yaml.safe_load(src.read_text(encoding="utf-8"))
    return [LegalReference(**item) for item in raw]


def for_section(section_key: str, audit_type: str | None = None) -> list[LegalReference]:
    """Return references applicable to `section_key`.

    A reference matches if:
      - its `section_keys` list contains `section_key`, OR
      - its `section_keys` list is empty (universal — applies everywhere)

    The `audit_type` filter is applied only when the reference explicitly
    restricts itself to specific types via `audit_types` — most don't, so
    most refs are returned regardless of audit_type.
    """
    refs = load_references()
    out = []
    for r in refs:
        if r.section_keys and section_key not in r.section_keys:
            continue
        if r.audit_types and audit_type is not None and audit_type not in r.audit_types:
            continue
        out.append(r)
    return out


def all_references() -> list[LegalReference]:
    """Full list of references — used by the 'Правовая база' browse page."""
    return load_references()
