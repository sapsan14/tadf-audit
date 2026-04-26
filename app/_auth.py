"""Login gate — call `require_login()` as the second-first thing on every page.

Two-source config:
  1. `st.secrets["auth_yaml"]` — for Streamlit Cloud (paste the whole yaml as
     a single multiline secret).
  2. `auth.yaml` in the repo root — for local dev.

The auth library (`streamlit-authenticator` 0.4+) sets:
  - `st.session_state["authentication_status"]` (True / False / None)
  - `st.session_state["name"]` (display name)
  - `st.session_state["username"]` (login key)

`require_login()` calls `authenticator.login()` (which renders the form AND
restores from cookie if present), then `st.stop()`s if the user isn't
authenticated. On every page. There is no way around it — direct URL
navigation also runs the page script, which calls this helper first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
import streamlit_authenticator as stauth
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
AUTH_YAML = REPO_ROOT / "auth.yaml"


def _load_config() -> dict[str, Any]:
    # Cloud first
    try:
        if "auth_yaml" in st.secrets:
            return yaml.safe_load(str(st.secrets["auth_yaml"]))
    except Exception:
        pass
    # Local dev
    if AUTH_YAML.exists():
        return yaml.safe_load(AUTH_YAML.read_text(encoding="utf-8"))
    raise RuntimeError(
        "No auth config found. Create auth.yaml from auth.yaml.example, "
        "or set st.secrets['auth_yaml'] on Streamlit Cloud."
    )


def _authenticator() -> stauth.Authenticate:
    """Construct fresh on every call.

    We can't @st.cache_resource this — the Authenticate constructor calls
    `stx.CookieManager()` which is a Streamlit widget, and Streamlit forbids
    widget calls inside cached functions. Reconstructing each rerun is
    cheap (just Python objects + a cookie read).
    """
    cfg = _load_config()
    return stauth.Authenticate(
        cfg["credentials"],
        cfg["cookie"]["name"],
        cfg["cookie"]["key"],
        cfg["cookie"].get("expiry_days", 30),
    )


def _ensure_session_keys() -> None:
    """streamlit-authenticator reads/writes specific keys; pre-init avoids
    KeyError on first render."""
    for k in ("authentication_status", "name", "username", "logout"):
        st.session_state.setdefault(k, None)


def require_login() -> stauth.Authenticate:
    """Block until the user is authenticated. Returns the authenticator
    so the caller can render a logout button.

    MUST be called from `app/main.py` (the entry script) — pages no longer
    call this themselves; the entry's call gates everything.
    """
    _ensure_session_keys()
    auth = _authenticator()
    try:
        auth.login(
            location="main",
            fields={
                "Form name": "🔐 TADF — вход",
                "Username": "E-mail (логин)",
                "Password": "Пароль",
                "Login": "Войти",
            },
        )
    except Exception as e:
        st.error(f"Ошибка авторизации: {e}")
        st.stop()

    status = st.session_state.get("authentication_status")
    if status is True:
        return auth
    if status is False:
        st.error("❌ Неверный логин или пароль.")
    else:
        st.info("Введите логин и пароль для входа в TADF Аудит.")
    st.stop()


def logout_button(auth: stauth.Authenticate, location: str = "sidebar") -> None:
    """Render a logout button. Call once after login is established."""
    import contextlib

    with contextlib.suppress(Exception):
        auth.logout("Выйти", location, key=f"logout_{location}")
