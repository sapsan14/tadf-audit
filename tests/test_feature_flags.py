"""Persistent feature-flag toggles."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def flags_module(tmp_path, monkeypatch):
    """Reload tadf.feature_flags with a temp file path so tests are isolated."""
    monkeypatch.setattr("tadf.config.DATA_DIR", tmp_path)
    import tadf.feature_flags as ff
    importlib.reload(ff)
    # Clean any test leftovers in env so default resolution is deterministic.
    monkeypatch.delenv("TADF_TEATMIK_ENABLED", raising=False)
    return ff


def test_teatmik_enabled_default_true(flags_module) -> None:
    assert flags_module.teatmik_enabled() is True


def test_env_overrides_default(flags_module, monkeypatch) -> None:
    monkeypatch.setenv("TADF_TEATMIK_ENABLED", "0")
    assert flags_module.teatmik_enabled() is False
    monkeypatch.setenv("TADF_TEATMIK_ENABLED", "yes")
    assert flags_module.teatmik_enabled() is True


def test_file_overrides_env(flags_module, monkeypatch) -> None:
    monkeypatch.setenv("TADF_TEATMIK_ENABLED", "1")
    flags_module.set_("teatmik_enabled", False)
    assert flags_module.teatmik_enabled() is False


def test_reset_drops_file_override(flags_module, monkeypatch) -> None:
    flags_module.set_("teatmik_enabled", False)
    assert flags_module.teatmik_enabled() is False
    flags_module.reset("teatmik_enabled")
    # Back to default
    assert flags_module.teatmik_enabled() is True


def test_unknown_flag_raises(flags_module) -> None:
    with pytest.raises(KeyError):
        flags_module.get("doesnt_exist")
    with pytest.raises(KeyError):
        flags_module.set_("doesnt_exist", True)


def test_corrupt_file_falls_back_gracefully(flags_module, tmp_path: Path) -> None:
    (tmp_path / "feature_flags.json").write_text("{ not valid json", encoding="utf-8")
    # Should not raise — falls through to env / default.
    assert flags_module.teatmik_enabled() is True
