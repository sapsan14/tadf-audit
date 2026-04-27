"""Round-trip + TTL behaviour for src/tadf/external/cache.py."""

from __future__ import annotations

import time

import pytest

from tadf.external.cache import cache_get, cache_key, cache_put


def test_cache_key_stable() -> None:
    """Same inputs → same key. Different inputs → different key."""
    a = cache_key("foo", "bar")
    b = cache_key("foo", "bar")
    c = cache_key("foo", "baz")
    assert a == b
    assert a != c
    assert len(a) == 32


def test_cache_key_separator_aware() -> None:
    """`("foo", "bar")` must NOT collide with `("foob", "ar")` — record
    separator avoids the classic concatenation collision."""
    a = cache_key("foo", "bar")
    b = cache_key("foob", "ar")
    assert a != b


def test_round_trip(tmp_path, monkeypatch) -> None:
    """Round-trip put → get returns the same value."""
    # Redirect cache root to tmp_path so we don't touch real data.
    monkeypatch.setattr("tadf.external.cache.CACHE_DIR", tmp_path)

    key = cache_key("test", "round-trip")
    value = {"hello": "world", "numbers": [1, 2, 3]}
    cache_put("test_ns", key, value)
    got = cache_get("test_ns", key)
    assert got == value


def test_get_missing_returns_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("tadf.external.cache.CACHE_DIR", tmp_path)
    assert cache_get("nonexistent_ns", "nokey") is None


def test_ttl_expiry(tmp_path, monkeypatch) -> None:
    """Entries past TTL are treated as missing AND deleted."""
    monkeypatch.setattr("tadf.external.cache.CACHE_DIR", tmp_path)
    key = cache_key("ttl", "test")
    cache_put("test_ns", key, {"data": 42})

    # Read with no TTL → still there.
    assert cache_get("test_ns", key) == {"data": 42}

    # Backdate the file's mtime by 31 days; with TTL=30 days it should expire.
    p = tmp_path / "test_ns" / f"{key}.json"
    assert p.exists()
    old = time.time() - 31 * 86400
    import os
    os.utime(p, (old, old))

    assert cache_get("test_ns", key, ttl_days=30) is None
    assert not p.exists()  # stale file was unlinked


def test_corrupt_json_returns_none(tmp_path, monkeypatch) -> None:
    """Corrupt cache file → None, not an exception."""
    monkeypatch.setattr("tadf.external.cache.CACHE_DIR", tmp_path)
    folder = tmp_path / "test_ns"
    folder.mkdir(parents=True)
    (folder / "abc.json").write_text("{not json", encoding="utf-8")
    assert cache_get("test_ns", "abc") is None


@pytest.mark.parametrize("ns", ["llm", "ehr", "extract", "with-dash"])
def test_namespace_isolation(tmp_path, monkeypatch, ns: str) -> None:
    """Different namespaces don't see each other's keys."""
    monkeypatch.setattr("tadf.external.cache.CACHE_DIR", tmp_path)
    cache_put(ns, "shared_key", {"in": ns})
    other = "other_" + ns
    assert cache_get(ns, "shared_key") == {"in": ns}
    assert cache_get(other, "shared_key") is None
