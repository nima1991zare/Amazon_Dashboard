"""
app.py — Amazon.ae Seller Management Dashboard
==============================================
Entry point: page config → DB init → login gate → sidebar nav → router.

Run (Windows PowerShell):
    python -m venv venv ; .\\venv\\Scripts\\Activate.ps1 ; pip install -r requirements.txt ; streamlit run app.py

Architecture: see README.md "Project structure". Every Amazon call goes through
core/api_client.py; every durable thing lives in core/db.py (SQLite). Pages live
in modules/ and expose a render(nav) function.
"""

from __future__ import annotations
import os
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="Amazon.ae Seller Command", page_icon="🛒",
                   layout="wide", initial_sidebar_state="expanded")

# Version shown in the sidebar + launcher terminal so you can confirm the build.
APP_VERSION = "1.5"


def _build_stamp() -> str:
    """Last-updated timestamp from the running file's own modification time."""
    try:
        ts = os.path.getmtime(os.path.abspath(__file__))
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""

from core import db
from core.auth import login_gate, logout
from core.styles import inject_global_css
from core import mock_data

from modules import (home, intake, optimization, stock, pricing, advertising,
                     market_analysis, deals, assets, aplus_studio, fba,
                     hazmat_inactive, events, orders_profit,
                     settings as settings_mod, ai_assistant)

# Page registry: label → (icon, render fn). Order = sidebar order.
PAGES = {
    "Home":                              ("🏠", home.render),
    "Inventory & Listing Intake":        ("📥", intake.render),
    "Listing Optimization":              ("🪄", optimization.render),
    "Stock Management":                  ("📦", stock.render),
    "Pricing":                           ("💰", pricing.render),
    "Advertising":                       ("📢", advertising.render),
    "Market Analysis":                   ("📊", market_analysis.render),
    "Deals":                             ("🔥", deals.render),
    "Asset Management":                  ("🎨", assets.render),
    "A+ Content Studio":                 ("✨", aplus_studio.render),
    "FBA / Warehouse Optimization":      ("🚚", fba.render),
    "Hazmat & Inactive":                 ("☣️", hazmat_inactive.render),
    "Event Planner":                     ("📅", events.render),
    "Orders & Profit":                   ("🧾", orders_profit.render),
    "AI Assistant":                      ("🤖", ai_assistant.render),
    "Settings":                          ("⚙️", settings_mod.render),
}


def _bootstrap() -> None:
    """One-time DB init + catalog seed so classification has a baseline."""
    if st.session_state.get("_booted"):
        return
    db.init_db()
    db.seed_catalog_if_empty(mock_data.catalog_seed())
    st.session_state["_booted"] = True


def _navigate(page_label: str) -> None:
    """Programmatic navigation used by Home task 'Go' buttons."""
    if page_label in PAGES:
        st.session_state["nav_choice"] = page_label
        st.rerun()


def _sidebar() -> str:
    with st.sidebar:
        st.markdown(
            "<div style='text-align:center; padding:6px 0 2px'>"
            "<div style='font-size:2rem'>🛒</div>"
            "<div style='font-weight:800; font-size:1.1rem'>Seller Command</div>"
            "<div style='color:var(--muted); font-size:.72rem'>Amazon.ae · Local-First</div></div>",
            unsafe_allow_html=True)
        st.markdown("---")
        st.markdown(
            f"<div style='font-size:.8rem; color:var(--muted)'>Signed in as</div>"
            f"<div style='font-weight:700; margin-bottom:6px'>👤 {st.session_state.get('username','admin')}</div>",
            unsafe_allow_html=True)

        labels = list(PAGES.keys())
        # Honor programmatic navigation requests.
        default_idx = labels.index(st.session_state.get("nav_choice", "Home")) \
            if st.session_state.get("nav_choice") in labels else 0
        if st.session_state.pop("goto_assistant", False):
            default_idx = labels.index("AI Assistant")

        choice = st.radio("Navigation", labels, index=default_idx,
                          format_func=lambda k: f"{PAGES[k][0]}  {k}",
                          label_visibility="collapsed", key="nav_radio")
        st.session_state["nav_choice"] = choice

        # Persistent AI quick-ask.
        ai_assistant.render_sidebar_quickask()

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚪 Logout", use_container_width=True):
                logout()
        with c2:
            open_n = db.count_open_tasks()
            st.markdown(f"<div style='text-align:center; padding-top:6px'>"
                        f"<span class='badge badge-coral'>{open_n} tasks</span></div>",
                        unsafe_allow_html=True)
        st.markdown(
            f"<div style='text-align:center; color:var(--muted); font-size:.7rem; margin-top:10px'>"
            f"v{APP_VERSION} · updated {_build_stamp()}</div>",
            unsafe_allow_html=True)
    return choice


def main() -> None:
    if not login_gate():
        return
    inject_global_css()
    _bootstrap()
    selected = _sidebar()
    _, render_fn = PAGES[selected]
    render_fn(_navigate)  # all modules accept nav (most ignore it)


if __name__ == "__main__":
    main()
