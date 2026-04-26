"""LLM helpers — Phase 2 of the TADF roadmap.

All four assistive features:
  - drafter:   bullet observations -> formal Estonian prose
  - captioner: photo + note -> Estonian caption + section_ref
  - ranker:    finding text -> ranked legal-ref codes (no inventing)
  - polish:    Estonian text -> polished Estonian text (grammar only)

API key resolution + persistent caching live in `client.py`. Sections 11
and 14 are hard-locked from drafter and polish — auditor only.
"""

from tadf.llm.captioner import caption_photo
from tadf.llm.client import MissingAPIKey, is_available
from tadf.llm.drafter import LOCKED_SECTIONS, draft_narrative, is_locked
from tadf.llm.polish import polish_text
from tadf.llm.ranker import rank_legal_refs

__all__ = [
    "LOCKED_SECTIONS",
    "MissingAPIKey",
    "caption_photo",
    "draft_narrative",
    "is_available",
    "is_locked",
    "polish_text",
    "rank_legal_refs",
]
