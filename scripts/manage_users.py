"""Add/update/remove users in `auth.yaml` from the CLI.

Why a script instead of a UI: account management is admin-only, infrequent,
and we don't want a browser-side flow that could be hijacked by a stolen
session cookie. Run this on the deploy host (or locally) where the
`auth.yaml` lives.

Examples
--------
Add a brand-new user (email is also the login key — that matches the form
label «E-mail (логин)»):

    uv run python scripts/manage_users.py add \\
        --username sokolovmeister@gmail.com \\
        --first-name Anton --last-name Sokolov \\
        --password tadf-anton-2026

Update an existing user's password (idempotent):

    uv run python scripts/manage_users.py set-password \\
        --username sokolovmeister@gmail.com \\
        --password new-password

List configured usernames (no passwords printed):

    uv run python scripts/manage_users.py list

Remove a user:

    uv run python scripts/manage_users.py remove --username old@example.com

The script is conservative: it never overwrites an unrelated key, never
prints a hash to stdout, and refuses to silently create `auth.yaml` —
copy `auth.yaml.example` first if it doesn't exist.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bcrypt
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_AUTH_YAML = REPO_ROOT / "auth.yaml"


def _hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _load(path: Path) -> dict:
    if not path.exists():
        sys.exit(
            f"❌ {path} не найден. Скопируйте auth.yaml.example в auth.yaml "
            "и заполните `cookie.key` перед использованием этого скрипта."
        )
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg.setdefault("credentials", {}).setdefault("usernames", {})
    return cfg


def _save(path: Path, cfg: dict) -> None:
    path.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def cmd_add(args: argparse.Namespace) -> None:
    cfg = _load(args.auth_yaml)
    users = cfg["credentials"]["usernames"]
    if args.username in users:
        sys.exit(
            f"❌ Пользователь {args.username!r} уже существует. "
            "Используйте `set-password` для обновления пароля."
        )
    users[args.username] = {
        "email": args.email or args.username,
        "first_name": args.first_name or "",
        "last_name": args.last_name or "",
        "logged_in": False,
        "roles": ["admin"],
        "password": _hash(args.password),
    }
    _save(args.auth_yaml, cfg)
    print(f"✅ Добавлен пользователь {args.username!r} (logged_in=False).")


def cmd_set_password(args: argparse.Namespace) -> None:
    cfg = _load(args.auth_yaml)
    users = cfg["credentials"]["usernames"]
    if args.username not in users:
        sys.exit(
            f"❌ Пользователь {args.username!r} не найден. "
            "Используйте `add` для создания."
        )
    users[args.username]["password"] = _hash(args.password)
    _save(args.auth_yaml, cfg)
    print(f"✅ Пароль для {args.username!r} обновлён.")


def cmd_remove(args: argparse.Namespace) -> None:
    cfg = _load(args.auth_yaml)
    users = cfg["credentials"]["usernames"]
    if users.pop(args.username, None) is None:
        sys.exit(f"❌ Пользователь {args.username!r} не найден.")
    _save(args.auth_yaml, cfg)
    print(f"✅ Пользователь {args.username!r} удалён.")


def cmd_list(args: argparse.Namespace) -> None:
    cfg = _load(args.auth_yaml)
    users = cfg["credentials"]["usernames"]
    if not users:
        print("(нет пользователей)")
        return
    for u, data in sorted(users.items()):
        print(f"- {u}\t{data.get('first_name', '')} {data.get('last_name', '')}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--auth-yaml",
        type=Path,
        default=DEFAULT_AUTH_YAML,
        help="Путь к auth.yaml (по умолчанию репо-корень).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Создать нового пользователя.")
    p_add.add_argument("--username", required=True, help="Логин (= e-mail).")
    p_add.add_argument("--password", required=True)
    p_add.add_argument("--email", help="По умолчанию = username.")
    p_add.add_argument("--first-name", default="")
    p_add.add_argument("--last-name", default="")
    p_add.set_defaults(func=cmd_add)

    p_pw = sub.add_parser("set-password", help="Обновить пароль существующего.")
    p_pw.add_argument("--username", required=True)
    p_pw.add_argument("--password", required=True)
    p_pw.set_defaults(func=cmd_set_password)

    p_rm = sub.add_parser("remove", help="Удалить пользователя.")
    p_rm.add_argument("--username", required=True)
    p_rm.set_defaults(func=cmd_remove)

    p_ls = sub.add_parser("list", help="Показать всех пользователей (без хэшей).")
    p_ls.set_defaults(func=cmd_list)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
