"""Render an Audit to a draft .docx via docxtpl + the master template."""

from __future__ import annotations

import json
from pathlib import Path

from docxtpl import DocxTemplate

from tadf.legal.checklist import check
from tadf.models import Audit
from tadf.render.context_builder import build_context
from tadf.templates import EA_KASUTUSEELNE


class ChecklistFailed(Exception):
    """Raised when § 5 mandatory fields are missing — block render."""

    def __init__(self, missing: list):
        self.missing = missing
        super().__init__("Audit fails §5 coverage:\n  " + "\n  ".join(str(m) for m in missing))


def render_to_path(
    audit: Audit,
    out_dir: Path,
    *,
    template_path: Path = EA_KASUTUSEELNE,
    enforce_checklist: bool = True,
) -> Path:
    """Render `audit` to `out_dir/draft.docx`. Also writes `context.json`."""
    out_dir.mkdir(parents=True, exist_ok=True)

    if enforce_checklist:
        missing = check(audit)
        if missing:
            raise ChecklistFailed(missing)

    ctx = build_context(audit)

    # Persist the exact context for reproducibility / 7-year retention.
    (out_dir / "context.json").write_text(
        json.dumps(ctx, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    tpl = DocxTemplate(str(template_path))
    tpl.render(ctx)
    out_path = out_dir / "draft.docx"
    tpl.save(str(out_path))
    return out_path
