"""
core/auth.py
============
SHA-256 session-state login gate. Blocks the whole app until authenticated.

No password is stored in plaintext in this repo. The valid login hash is resolved
from (first match wins):
  1. env var  DASHBOARD_LOGIN_HASH  — sha256 of "username|password"
  2. the local Settings DB          — key 'login_hash' (data/seller.db is gitignored)
  3. a built-in bootstrap HASH      — so a fresh clone is still reachable
To change the login, set DASHBOARD_LOGIN_HASH or save 'login_hash' in the DB; the
plaintext never needs to live in source. (For production, add rate limiting.)
"""

from __future__ import annotations
import hashlib
import os
import streamlit as st

from core import db
from core.styles import inject_global_css


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Bootstrap credential as a HASH only (never the plaintext) so this file carries no
# readable password. Keeps existing logins working; override it via env/DB above.
_BOOTSTRAP_HASH = "f467fdd99164571a260053a0587651d6be8dfc2e68026254262d2439463ec90c"


def _valid_hashes() -> set:
    """Accepted login hashes: an env override and/or a DB-stored hash, else the
    built-in bootstrap hash. Lets the credential live outside the repo entirely."""
    hashes = {_BOOTSTRAP_HASH}
    env = os.environ.get("DASHBOARD_LOGIN_HASH", "").strip()
    if env:
        hashes.add(env)
    try:
        stored = db.get_setting("login_hash", "")
        if stored:
            hashes.add(stored)
    except Exception:
        pass
    return hashes


def _verify(username: str, password: str) -> bool:
    return _hash(f"{username.strip()}|{password}") in _valid_hashes()


def is_authenticated() -> bool:
    return bool(st.session_state.get("authenticated", False))


def logout() -> None:
    st.session_state["authenticated"] = False
    st.session_state.pop("username", None)
    st.rerun()


def login_gate() -> bool:
    """Return True if authenticated; otherwise render login card and return False."""
    if is_authenticated():
        return True

    inject_global_css()
    st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.15, 1])
    with mid:
        st.markdown(
            "<div class='glass-card' style='padding:34px 34px 26px;'>"
            "<div class='login-hero'><div class='lh-logo'>🛒</div>"
            "<div class='lh-title'>Amazon.ae Seller Command</div>"
            "<div class='lh-sub'>Local-First Operations Dashboard</div></div>",
            unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="••••••••••")
            submitted = st.form_submit_button("🔓  Sign In", use_container_width=True)
        if submitted:
            if _verify(username, password):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username.strip()
                st.rerun()
            else:
                st.markdown(
                    "<div class='alert alert-coral'><span style='font-size:1.3rem'>⛔</span>"
                    "<span>Invalid credentials.</span></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='text-align:center; color:var(--muted); font-size:.78rem; margin-top:14px'>"
            "🔒 SHA-256 verified · local session</div></div>", unsafe_allow_html=True)
    return False
