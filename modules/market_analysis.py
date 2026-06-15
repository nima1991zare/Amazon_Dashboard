"""
modules/market_analysis.py
==========================
📊 Market Analysis (Module 7).

Compares your items vs the Amazon market, flags items that are trending AND
well-priced (→ suggest A+ content + ads), and recommends other levers per item
(e.g. "set a 10% coupon"). Findings feed into the central Tasks table.
"""

from __future__ import annotations
import streamlit as st

from core import db
from core.api_client import client
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge, alert


def _lever(row) -> str:
    """Recommend a growth lever per item from its signal + price gap."""
    if row["signal"] in ("Trending", "Hidden Gem") and row["your_price"] <= row["market_min"] * 1.05:
        return "Add A+ content + run ads"
    if row["your_price"] > row["market_min"] * 1.1:
        return "Set 10% coupon (price gap)"
    if row["signal"] == "Declining":
        return "Deal or clearance"
    return "Hold"


def render(nav=None) -> None:
    page_header("Market Analysis", "Where you stand vs the market — and what to do",
                icon="📊")
    df = client().get_market_comparison().copy()
    df["lever"] = df.apply(_lever, axis=1)
    df["price_gap"] = (df["your_price"] - df["market_min"]).round(0)

    trending = df[df["signal"].isin(["Trending", "Hidden Gem"])]
    kpi_row([
        {"label": "Items Analyzed", "value": str(len(df)), "accent": "blue"},
        {"label": "Trending", "value": str(len(trending)), "accent": "emerald",
         "sub": "Promote these"},
        {"label": "Overpriced vs Market",
         "value": str(int((df["your_price"] > df["market_min"] * 1.1).sum())),
         "accent": "amber", "sub": "Coupon candidates"},
    ])
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    if not trending.empty:
        st.markdown(alert(f"{len(trending)} trending + well-priced items — prime for A+ "
                          f"content and ads.", kind="green", icon="🚀"), unsafe_allow_html=True)

    st.markdown(section_label("Your Items vs Market"), unsafe_allow_html=True)
    styled_table(df, highlight={
        "row-good": lambda r: r["signal"] in ("Trending", "Hidden Gem"),
        "row-warn": lambda r: r["signal"] == "Declining"},
        badge_cols={"lever": {
            "Add A+ content + run ads": ("🚀 A+ & Ads", "green"),
            "Set 10% coupon (price gap)": ("🎟️ 10% Coupon", "blue"),
            "Deal or clearance": ("🔥 Deal", "amber"),
            "Hold": ("→ Hold", "violet")},
            "signal": {"Trending": ("Trending", "green"), "Hidden Gem": ("Hidden Gem", "green"),
                       "Stable": ("Stable", "blue"), "Declining": ("Declining", "amber")}})
    export_buttons(df, "market_analysis")

    if st.button("➕ Turn recommendations into Tasks"):
        for _, r in df[df["lever"] != "Hold"].iterrows():
            db.add_task(f"{r['lever']}: {r['item']}",
                        f"Signal {r['signal']}, you AED {r['your_price']} vs market AED {r['market_min']}.",
                        module="Market Analysis", priority="medium", related_id=r["item"])
        st.success("Recommendations added to Tasks.")
