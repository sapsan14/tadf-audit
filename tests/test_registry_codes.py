"""Estonian reg-code and isikukood checksum validators."""

from __future__ import annotations

from tadf.external.registry_codes import (
    id_code_hint,
    is_valid_id_code,
    is_valid_reg_code,
    reg_code_hint,
)

# Real Estonian registry codes (publicly searchable on Ariregister) and a
# synthetic body whose mod-11 check digit was hand-computed.
KNOWN_VALID_REG_CODES = [
    "10137319",  # AS Tallinna Sadam (real)
    "12345678",  # synthetic: body 1234567 -> mod-11 = 8
    "10101009",  # synthetic: body 1010100 -> mod-11 = 9
]


def test_reg_code_known_valid() -> None:
    for code in KNOWN_VALID_REG_CODES:
        assert is_valid_reg_code(code), code


def test_reg_code_typo_caught() -> None:
    assert not is_valid_reg_code("10137310")  # last digit off
    assert not is_valid_reg_code("12345670")  # last digit off
    assert not is_valid_reg_code("10137419")  # interior digit changed


def test_reg_code_wrong_length() -> None:
    assert not is_valid_reg_code("1000604")
    assert not is_valid_reg_code("100060400")
    assert not is_valid_reg_code("")
    assert not is_valid_reg_code(None)


def test_reg_code_non_digit() -> None:
    assert not is_valid_reg_code("abcdefgh")
    assert not is_valid_reg_code("1000-604")
    assert not is_valid_reg_code(" 10006040")  # validator must trim — but spaces inside fail


def test_reg_code_strips_whitespace() -> None:
    assert is_valid_reg_code("  10137319  ")


def test_reg_code_hint_messages() -> None:
    assert reg_code_hint(None) is None
    assert reg_code_hint("") is None
    assert reg_code_hint("   ") is None
    assert reg_code_hint("10137319") is None  # valid -> no hint
    assert "цифр" in (reg_code_hint("abc") or "")
    assert "8 цифр" in (reg_code_hint("123") or "")
    assert "опечатка" in (reg_code_hint("10137310") or "")


# Real-shaped Estonian personal codes; first digit encodes century+gender.
# These are checksum-valid synthetic examples for unit testing only.
def test_id_code_validates_known_form() -> None:
    # Synthesised so the mod-11 check passes — algorithm-only test.
    # 38001085718 is from RIK's public test fixtures.
    assert is_valid_id_code("38001085718")


def test_id_code_typo_caught() -> None:
    assert not is_valid_id_code("38001085719")
    assert not is_valid_id_code("48001085718")


def test_id_code_wrong_length() -> None:
    assert not is_valid_id_code("3800108571")
    assert not is_valid_id_code("380010857180")
    assert not is_valid_id_code(None)


def test_id_code_hint_messages() -> None:
    assert id_code_hint(None) is None
    assert id_code_hint("38001085718") is None
    assert "11 цифр" in (id_code_hint("123") or "")
    assert "опечатка" in (id_code_hint("38001085719") or "")
