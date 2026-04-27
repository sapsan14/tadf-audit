"""End-to-end exercise of `scripts/manage_users.py` against a temp YAML."""

from __future__ import annotations

import sys
from pathlib import Path

import bcrypt
import pytest
import yaml

# scripts/ isn't on sys.path by default; pull manage_users in directly.
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import manage_users  # noqa: E402


@pytest.fixture
def fresh_yaml(tmp_path) -> Path:
    p = tmp_path / "auth.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "credentials": {"usernames": {}},
                "cookie": {"name": "tadf_auth", "key": "k", "expiry_days": 30},
            }
        ),
        encoding="utf-8",
    )
    return p


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_add_then_set_password_then_remove(fresh_yaml) -> None:
    manage_users.main(
        [
            "--auth-yaml",
            str(fresh_yaml),
            "add",
            "--username",
            "alice@example.com",
            "--password",
            "pw1",
            "--first-name",
            "Alice",
        ]
    )
    cfg = _read(fresh_yaml)
    user = cfg["credentials"]["usernames"]["alice@example.com"]
    assert user["first_name"] == "Alice"
    assert user["email"] == "alice@example.com"
    # Password is bcrypt-verifiable.
    assert bcrypt.checkpw(b"pw1", user["password"].encode("utf-8"))

    # Updating the password preserves the rest of the record.
    manage_users.main(
        [
            "--auth-yaml",
            str(fresh_yaml),
            "set-password",
            "--username",
            "alice@example.com",
            "--password",
            "pw2",
        ]
    )
    cfg = _read(fresh_yaml)
    user = cfg["credentials"]["usernames"]["alice@example.com"]
    assert user["first_name"] == "Alice"  # untouched
    assert bcrypt.checkpw(b"pw2", user["password"].encode("utf-8"))
    assert not bcrypt.checkpw(b"pw1", user["password"].encode("utf-8"))

    # Remove returns the user dict to empty.
    manage_users.main(
        ["--auth-yaml", str(fresh_yaml), "remove", "--username", "alice@example.com"]
    )
    cfg = _read(fresh_yaml)
    assert cfg["credentials"]["usernames"] == {}


def test_add_existing_user_exits(fresh_yaml) -> None:
    manage_users.main(
        [
            "--auth-yaml",
            str(fresh_yaml),
            "add",
            "--username",
            "bob",
            "--password",
            "x",
        ]
    )
    with pytest.raises(SystemExit):
        manage_users.main(
            [
                "--auth-yaml",
                str(fresh_yaml),
                "add",
                "--username",
                "bob",
                "--password",
                "y",
            ]
        )


def test_set_password_unknown_user_exits(fresh_yaml) -> None:
    with pytest.raises(SystemExit):
        manage_users.main(
            [
                "--auth-yaml",
                str(fresh_yaml),
                "set-password",
                "--username",
                "ghost",
                "--password",
                "x",
            ]
        )


def test_missing_yaml_exits_cleanly(tmp_path) -> None:
    nonexistent = tmp_path / "nope.yaml"
    with pytest.raises(SystemExit):
        manage_users.main(
            [
                "--auth-yaml",
                str(nonexistent),
                "list",
            ]
        )
