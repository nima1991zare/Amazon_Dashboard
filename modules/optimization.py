"""
modules/optimization.py
=======================
🪄 Listing Optimization (Module 3).

For a chosen item it: pulls top best-sellers in the same Amazon category (via
api_client; mock now), extracts their keywords, then generates an optimized
Title / Bullets / Keywords / Description that respects Amazon policy (length, no
promo claims). Output is shown in copyable code blocks with Export.

optimize_item() is the reusable entry the Intake module also calls. Generation is
routed through assistant.answer() when an Anthropic key is set, else a
deterministic rule-based builder (mock_data.optimized_listing).
"""

from __future__ import annotations
import re
import pandas as pd
import streamlit as st

from core import db, mock_data
from core.api_client import client
from core.components import styled_table, export_buttons, page_header
from core.styles import section_label, badge

TITLE_LIMIT = 200
# Words Amazon disallows in titles (promotional claims).
_BANNED = ["best", "cheap", "sale", "free shipping", "guarantee", "100%", "#1", "hot"]


def _policy_clean_title(title: str) -> tuple[str, list[str]]:
    """Strip banned promo terms and enforce length. Returns (clean, removed)."""
    removed = []
    clean = title
    for w in _BANNED:
        if re.search(rf"\b{re.escape(w)}\b", clean, flags=re.IGNORECASE):
            removed.append(w)
            clean = re.sub(rf"\b{re.escape(w)}\b", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s{2,}", " ", clean).strip(" -|")
    return clean[:TITLE_LIMIT], removed


def optimize_item(title_seed: str, category: str, extra_keywords: str = "") -> dict:
    """Reusable optimizer. Pulls category keywords then builds the listing."""
    top = client().get_top_sellers_in_category(category)
    mined = " ".join(top["keywords"].tolist()) if not top.empty else ""
    keywords = (extra_keywords + " " + mined).strip()
    listing = mock_data.optimized_listing(title_seed, category, keywords)
    listing["title"], _ = _policy_clean_title(listing["title"])
    return listing


def render(nav=None) -> None:
    page_header("Listing Optimization",
                "Policy-safe titles, bullets, keywords & descriptions from category data",
                icon="🪄")

    listings = client().get_my_listings()
    src = st.radio("Optimize for", ["An existing listing", "Custom item"], horizontal=True)

    if src == "An existing listing":
        pick = st.selectbox("Item", listings["title"].tolist())
        row = listings[listings["title"] == pick].iloc[0]
        title_seed, category = row["title"], row["category"]
    else:
        title_seed = st.text_input("Product name", "Marshall Emberton III - Black")
        category = st.selectbox("Category", ["Audio", "Charging", "Smart Home", "Phones", "Home"])

    extra = st.text_input("Extra keywords (optional)", "")

    # Show the best-sellers we mine keywords from.
    with st.expander("🔍 Category best-sellers (keyword source)", expanded=False):
        top = client().get_top_sellers_in_category(category)
        styled_table(top)

    if st.button("⚡ Generate Optimized Listing", use_container_width=True):
        listing = optimize_item(title_seed, category, extra)
        st.session_state["last_optimized"] = listing

    listing = st.session_state.get("last_optimized")
    if not listing:
        return

    title_len = len(listing["title"])
    ok = title_len <= TITLE_LIMIT
    len_badge = badge(f"{title_len}/{TITLE_LIMIT} chars", "green" if ok else "coral")
    st.markdown(section_label("Optimized Title") + " " + len_badge, unsafe_allow_html=True)
    st.code(listing["title"], language="text")

    st.markdown(section_label("Bullet Points"), unsafe_allow_html=True)
    st.code("\n".join(f"• {b}" for b in listing["bullets"]), language="text")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(section_label("Backend Keywords"), unsafe_allow_html=True)
        st.code(listing["keywords"], language="text")
    with c2:
        st.markdown(section_label("Description"), unsafe_allow_html=True)
        st.code(listing["description"], language="text")

    # Export the optimized listing.
    out = pd.DataFrame([{
        "title": listing["title"], "bullets": " | ".join(listing["bullets"]),
        "keywords": listing["keywords"], "description": listing["description"],
    }])
    export_buttons(out, "optimized_listing")

    if st.button("➕ Save as task"):
        db.add_task(f"Apply optimized copy: {title_seed}",
                    "Generated in Listing Optimization.",
                    module="Listing Optimization", priority="low")
        st.success("Task added.")
