"""Validators for Estonian registry / personal codes.

Used in UI to warn the auditor about typos before we hit Ariregister or
treat a value as a real isikukood. Validation is advisory — the model
layer never refuses a value, callers decide what to do with `is_valid_*`.
"""

from __future__ import annotations


def _weighted_check(body: list[int], weights1: list[int], weights2: list[int]) -> int:
    s1 = sum(d * w for d, w in zip(body, weights1, strict=True)) % 11
    if s1 < 10:
        return s1
    s2 = sum(d * w for d, w in zip(body, weights2, strict=True)) % 11
    if s2 < 10:
        return s2
    return 0


def is_valid_reg_code(code: str | None) -> bool:
    """8-digit Estonian legal-person registry code (registrikood) checksum.

    https://www.rik.ee/en/e-business-register — the 8th digit is the
    standard mod-11 / mod-3-fallback check over the first seven.
    """
    s = (code or "").strip()
    if not s.isdigit() or len(s) != 8:
        return False
    digits = [int(c) for c in s]
    body, check = digits[:7], digits[7]
    return _weighted_check(body, [1, 2, 3, 4, 5, 6, 7], [3, 4, 5, 6, 7, 8, 9]) == check


def is_valid_id_code(code: str | None) -> bool:
    """11-digit Estonian personal identification code (isikukood) checksum.

    First digit (gender + century) is part of the body for the checksum;
    weights are the standard sequence used by the Population Register.
    """
    s = (code or "").strip()
    if not s.isdigit() or len(s) != 11:
        return False
    digits = [int(c) for c in s]
    body, check = digits[:10], digits[10]
    weights1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 1]
    weights2 = [3, 4, 5, 6, 7, 8, 9, 1, 2, 3]
    return _weighted_check(body, weights1, weights2) == check


def reg_code_hint(code: str | None) -> str | None:
    """Human-readable warning string, or None when input is valid/empty.

    Returned text is meant for `st.caption` / `st.warning` next to the
    input field. Empty input is treated as "no opinion" — this is an
    optional field.
    """
    s = (code or "").strip()
    if not s:
        return None
    if not s.isdigit():
        return "Рег-код должен состоять только из цифр."
    if len(s) != 8:
        return f"Рег-код должен быть 8 цифр (введено {len(s)})."
    if not is_valid_reg_code(s):
        return "Контрольная цифра рег-кода не сходится — возможно опечатка."
    return None


def id_code_hint(code: str | None) -> str | None:
    """Same as `reg_code_hint`, for 11-digit isikukood."""
    s = (code or "").strip()
    if not s:
        return None
    if not s.isdigit():
        return "Isikukood должен состоять только из цифр."
    if len(s) != 11:
        return f"Isikukood должен быть 11 цифр (введено {len(s)})."
    if not is_valid_id_code(s):
        return "Контрольная цифра isikukood не сходится — возможно опечатка."
    return None


__all__ = [
    "id_code_hint",
    "is_valid_id_code",
    "is_valid_reg_code",
    "reg_code_hint",
]
