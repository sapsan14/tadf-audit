"""One-click 'улучшить' helper that picks the right LLM operation.

Heuristic:
- empty -> raise (UI must disable the button beforehand)
- locked section (11/14) -> raise (UI must also disable beforehand)
- мостовая кириллица (>20% букв) -> draft_narrative as RU→ET translator
  (drafter's system prompt explicitly handles RU input by translating to
  Estonian construction terminology)
- короткие тезисы (<30 слов AND newline OR bullet marker) -> draft_narrative
- otherwise -> polish_text (Estonian grammar/style fix)
"""

from __future__ import annotations

from dataclasses import dataclass

from tadf.llm.drafter import draft_narrative, is_locked
from tadf.llm.polish import polish_text


@dataclass(frozen=True)
class ImproveResult:
    action: str  # "polish" | "draft" | "translate"
    original: str
    improved: str

    @property
    def label_ru(self) -> str:
        return {
            "polish": "Эстонская грамматика / стиль",
            "draft": "Тезисы → формальный параграф",
            "translate": "Перевод RU → ET",
        }.get(self.action, self.action)


def _cyrillic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    return cyr / len(letters)


def _looks_like_bullets(text: str) -> bool:
    stripped = text.lstrip()
    if any(stripped.startswith(m) for m in ("- ", "• ", "* ")):
        return True
    return bool("\n" in text and len(text.split()) < 30)


def improve_text(text: str, *, section_ref: str | None = None) -> ImproveResult:
    text = text.strip()
    if not text:
        raise ValueError("Поле пустое — нечего улучшать.")
    if section_ref and is_locked(section_ref):
        raise ValueError(
            f"Раздел {section_ref} — только аудитор, ИИ выключен."
        )

    fallback_section = section_ref or "general"

    if _cyrillic_ratio(text) > 0.2:
        return ImproveResult(
            action="translate",
            original=text,
            improved=draft_narrative(fallback_section, text),
        )
    if _looks_like_bullets(text):
        return ImproveResult(
            action="draft",
            original=text,
            improved=draft_narrative(fallback_section, text),
        )
    return ImproveResult(
        action="polish",
        original=text,
        improved=polish_text(text, section_ref=section_ref),
    )
