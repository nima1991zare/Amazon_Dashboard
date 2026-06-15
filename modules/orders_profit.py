"""
modules/orders_profit.py
========================
🧾 Orders & Profit (Module 12).

  * Orders table (id, date, item, qty, status, revenue) with Export.
  * Per-item profit = revenue − cost − ad spend; overall margin.
  * Charts: profit over time, top/bottom profit items (plotly).
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import streamlit as st

from core.api_client import client
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, PALETTE

_DARK = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
             plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=30, b=10))


def render(nav=None) -> None:
    page_header("Orders & Profit", "Every order, every item's margin, at a glance", icon="🧾")
    orders = client().get_orders().copy()
    orders["profit"] = orders["revenue"] - orders["cost"] - orders["ad_spend"]

    rev, profit = orders["revenue"].sum(), orders["profit"].sum()
    margin = (profit / rev * 100) if rev else 0
    kpi_row([
        {"label": "Revenue", "value": f"AED {rev:,.0f}", "accent": "blue"},
        {"label": "Profit", "value": f"AED {profit:,.0f}",
         "accent": "emerald" if profit >= 0 else "coral"},
        {"label": "Margin", "value": f"{margin:.1f}%",
         "accent": "emerald" if margin >= 15 else "amber"},
        {"label": "Orders", "value": str(len(orders)), "accent": "violet"},
    ])

    tabs = st.tabs(["📋 Orders", "💵 Per-item Profit", "📈 Charts"])

    with tabs[0]:
        disp = orders[["order_id", "date", "item", "qty", "status", "revenue"]].copy()
        disp["revenue"] = disp["revenue"].map(lambda v: f"AED {v:,.0f}")
        styled_table(disp, highlight={"row-good": lambda r: r["status"] == "Shipped"})
        export_buttons(orders, "orders")

    with tabs[1]:
        per = orders.groupby("item", as_index=False).agg(
            revenue=("revenue", "sum"), cost=("cost", "sum"),
            ad_spend=("ad_spend", "sum"), profit=("profit", "sum"))
        per["margin_%"] = (per["profit"] / per["revenue"] * 100).round(1)
        per = per.sort_values("profit", ascending=False)
        styled_table(per, highlight={
            "row-good": lambda r: r["profit"] > 0,
            "row-danger": lambda r: r["profit"] <= 0})
        export_buttons(per, "profit_by_item")

    with tabs[2]:
        st.markdown(section_label("Profit Over Time"), unsafe_allow_html=True)
        daily = orders.groupby("date", as_index=False)["profit"].sum()
        fig1 = px.area(daily, x="date", y="profit", markers=True,
                       color_discrete_sequence=[PALETTE["emerald"]])
        fig1.update_layout(**_DARK, height=300)
        st.plotly_chart(fig1, use_container_width=True)

        st.markdown(section_label("Profit by Item"), unsafe_allow_html=True)
        per = orders.groupby("item", as_index=False)["profit"].sum().sort_values("profit")
        fig2 = px.bar(per, x="profit", y="item", orientation="h",
                      color="profit", color_continuous_scale=["#ff5d6c", "#10e0a0"])
        fig2.update_layout(**_DARK, height=340, coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)
