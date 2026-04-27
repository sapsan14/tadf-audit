"""HMAC tokens for the import API — round-trip + tamper resistance."""

from __future__ import annotations

import os

import pytest

# Set a fixed secret BEFORE importing the module so we exercise the
# env-var path, not the per-process random fallback.
os.environ["TADF_IMPORT_SECRET"] = "test-secret-do-not-deploy"

from tadf.api.tokens import issue, verify  # noqa: E402


def test_round_trip_basic() -> None:
    t = issue(42)
    assert verify(t) == 42


def test_different_audits_get_different_tokens() -> None:
    a = issue(1)
    b = issue(2)
    assert a != b
    assert verify(a) == 1
    assert verify(b) == 2


def test_garbage_returns_none() -> None:
    assert verify("") is None
    assert verify("definitely not a token") is None
    assert verify("a:b:c:d") is None  # too many parts


def test_tampered_signature_rejected() -> None:
    t = issue(99)
    parts = t.split(":")
    parts[2] = "0" * len(parts[2])
    bad = ":".join(parts)
    assert verify(bad) is None


def test_tampered_audit_id_rejected() -> None:
    t = issue(99)
    parts = t.split(":")
    parts[0] = "100"
    assert verify(":".join(parts)) is None


def test_expired_token_rejected() -> None:
    t = issue(7, ttl_seconds=-1)
    assert verify(t) is None


def test_token_format() -> None:
    t = issue(123)
    parts = t.split(":")
    assert len(parts) == 3
    assert parts[0] == "123"
    assert parts[1].isdigit()
    assert len(parts[2]) == 32  # truncated sha256


@pytest.mark.parametrize("audit_id", [0, 1, 99, 999_999])
def test_various_audit_ids(audit_id: int) -> None:
    assert verify(issue(audit_id)) == audit_id
