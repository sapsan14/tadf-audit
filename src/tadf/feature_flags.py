"""Runtime feature flags persisted to a small JSON file.

Designed for the migration off teatmik.ee → ariregister: the auditor
should be able to flip back to the old flow from the «Подключения»
page without restarting the app or editing env vars. Keeping the
mechanism generic so other ON/OFF toggles can join later.

Resolution order (first non-None wins):
  1. JSON file at `<DATA_DIR>/feature_flags.json` (UI-controlled)
  2. Environment variable (CI / containers)
  3. Hard-coded default below

Writes are atomic via tmp+rename, same as `external/cache.py`.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from tadf.config import DATA_DIR

log = logging.getLogger(__name__)

_FLAGS_PATH: Path = DATA_DIR / "feature_flags.json"

# (env_var, default_when_unset)
_FLAG_DEFAULTS: dict[str, tuple[str, bool]] = {
    # During migration we keep teatmik on by default so nobody is suddenly
    # cut off; the «Подключения» page is the supported way to flip it off
    # once Ariregister credentials are in. Once we've shipped a release
    # that's been used for ≥1 month with teatmik off, default flips to False.
    "teatmik_enabled": ("TADF_TEATMIK_ENABLED", True),
}


def _read_file() -> dict[str, Any]:
    if not _FLAGS_PATH.exists():
        return {}
    try:
        return json.loads(_FLAGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("Could not read %s: %s — falling back to env/defaults", _FLAGS_PATH, e)
        return {}


def _write_file(flags: dict[str, Any]) -> None:
    _FLAGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FLAGS_PATH.with_suffix(_FLAGS_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(flags, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_FLAGS_PATH)


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
    return None


def get(name: str) -> bool:
    """Resolve a flag's current value via file → env → default."""
    if name not in _FLAG_DEFAULTS:
        raise KeyError(f"Unknown feature flag: {name!r}")
    env_var, default = _FLAG_DEFAULTS[name]

    file_flags = _read_file()
    if name in file_flags:
        c = _coerce_bool(file_flags[name])
        if c is not None:
            return c

    env_val = os.environ.get(env_var)
    if env_val is not None:
        c = _coerce_bool(env_val)
        if c is not None:
            return c

    return default


def set_(name: str, value: bool) -> None:
    """Persist a flag value to the JSON file (UI tumbler entry point)."""
    if name not in _FLAG_DEFAULTS:
        raise KeyError(f"Unknown feature flag: {name!r}")
    flags = _read_file()
    flags[name] = bool(value)
    _write_file(flags)


def reset(name: str) -> None:
    """Drop the file override for a flag — env / default takes over."""
    flags = _read_file()
    if name in flags:
        del flags[name]
        _write_file(flags)


def teatmik_enabled() -> bool:
    """Convenience accessor for the flag used across pages 1, 2, 7."""
    return get("teatmik_enabled")


__all__ = [
    "get",
    "reset",
    "set_",
    "teatmik_enabled",
]
