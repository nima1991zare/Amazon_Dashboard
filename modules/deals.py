"""
modules/deals.py
================
🔥 Deals (Module 8).

Pulls Amazon's suggested-for-deals items (api_client; mock) and recommends the
best deal price per item, showing the resulting margin. Export + push to Tasks.
"""

from __future__ import annotations
import streamlit as st

from core import db
from core.api_client import client
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge


def render(nav=None) -> None:
    page_header("Deals", "Amazon deal candidates and the best price to offer", icon="🔥")
    df = client().get_deal_suggestions().copy()
    df["discount_%"] = ((1 - df["suggested_deal_price"] / df["current_price"]) * 100).round(0)

    kpi_row([
        {"label": "Deal Candidates", "value": str(len(df)), "accent": "blue"},
        {"label": "Avg Discount", "value": f"{df['discount_%'].mean():.0f}%", "accent": "amber"},
        {"label": "Min Margin Kept", "value": f"{df['margin_pct'].min():.0f}%", "accent": "emerald"},
    ])
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown(section_label("Suggested Deals"), unsafe_allow_html=True)
    styled_table(df, highlight={"row-good": lambda r: r["margin_pct"] >= 30},
                 badge_cols={"deal_type": {
                     "Lightning Deal": ("⚡ Lightning", "violet"),
                     "7-Day Deal": ("📅 7-Day", "blue"),
                     "Best Deal": ("🏆 Best Deal", "green")}})
    export_buttons(df, "deal_suggestions")

    if st.button("➕ Add deals to Tasks"):
        for _, r in df.iterrows():
            db.add_task(f"Submit {r['deal_type']}: {r['item']}",
                        f"Deal price AED {r['suggested_deal_price']} "
                        f"(−{r['discount_%']:.0f}%), keeps {r['margin_pct']}% margin.",
                        module="Deals", priority="medium", related_id=r["item"])
        st.success("Deals added to Tasks.")
