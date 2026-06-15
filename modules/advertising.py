"""
modules/advertising.py
======================
📢 Advertising (Module 6).

  * Campaign overview (Ads API; mock): spend, ACoS, impressions, sales + KPIs.
  * Budget alarms: flashing banner + email/telegram when a campaign spends >20%
    over its daily average.
  * Prebuilt campaign generator: build a campaign from ad assets + trending
    keywords/products (api_client.create_campaign stub).
  * Ad Optimization: suggested bids per keyword/target and which ads to run.
"""

from __future__ import annotations
import pandas as pd
import streamlit as st

from core import db, notifier
from core.api_client import client
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, alert, badge

OVER = 1.20


def _overview(ads: pd.DataFrame) -> None:
    spend, sales = ads["spend_today"].sum(), ads["sales"].sum()
    acos = (spend / sales * 100) if sales else 0
    kpi_row([
        {"label": "Spend Today", "value": f"AED {spend:,.0f}", "accent": "blue"},
        {"label": "Ad Sales", "value": f"AED {sales:,.0f}", "accent": "emerald"},
        {"label": "Blended ACoS", "value": f"{acos:.1f}%",
         "accent": "amber" if acos > 20 else "emerald", "sub": "Target ≤ 20%"},
        {"label": "Impressions", "value": f"{ads['impressions'].sum()/1000:.1f}K",
         "accent": "violet"},
    ])


def _budget_alarm(ads: pd.DataFrame) -> None:
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    over = ads[ads["spend_today"] > ads["avg_daily"] * OVER]
    if over.empty:
        st.markdown(alert("All campaigns within budget guardrails.", kind="green", icon="✅"),
                    unsafe_allow_html=True)
        return
    names = ", ".join(over["campaign"].tolist())
    st.markdown(alert(f"BUDGET ALARM — {len(over)} campaign(s) >20% over daily avg: {names}",
                      kind="coral", icon="🚨", flash=True), unsafe_allow_html=True)
    c = st.columns([1, 1, 2])
    with c[0]:
        if st.button("➕ Add to Tasks", key="ad_task"):
            for _, r in over.iterrows():
                db.add_task(f"Cap budget: {r['campaign']}",
                            f"AED {r['spend_today']} vs AED {r['avg_daily']} avg.",
                            module="Advertising", priority="medium", related_id=r["campaign"])
            st.success("Tasks added.")
    with c[1]:
        if st.button("🔔 Notify", key="ad_notify"):
            res = notifier.notify_event("budget", "Ad budget alarm",
                                        f"Over budget: {names}")
            for ch, ok, msg in res:
                (st.success if ok else st.warning)(f"{ch}: {msg}")


def _table(ads: pd.DataFrame) -> None:
    st.markdown(section_label("📈 Campaigns"), unsafe_allow_html=True)
    disp = ads.copy()
    disp["over"] = disp.apply(lambda r: "Over" if r["spend_today"] > r["avg_daily"] * OVER else "OK", axis=1)
    styled_table(disp, highlight={
        "row-danger": lambda r: r["over"] == "Over",
        "row-warn": lambda r: r["acos"] > 25},
        badge_cols={"over": {"Over": ("⚠ Over", "coral"), "OK": ("✓ OK", "green")}})
    export_buttons(disp, "campaigns")


def _generator() -> None:
    st.markdown(section_label("🧱 Prebuilt Campaign Generator"), unsafe_allow_html=True)
    listings = client().get_my_listings()
    item = st.selectbox("Item to advertise", listings["title"].tolist(), key="gen_item")
    ctype = st.selectbox("Campaign type", ["Sponsored Products - Auto",
                                           "Sponsored Products - Exact", "Sponsored Brands"])
    budget = st.number_input("Daily budget (AED)", 10.0, value=150.0, step=10.0)

    row = listings[listings["title"] == item].iloc[0]
    targets = client().get_keyword_targets(item)
    st.caption("Suggested targets (trending keywords for this item):")
    styled_table(targets)

    if st.button("🚀 Build Campaign"):
        payload = {"name": f"{ctype.split(' - ')[0]} - {item}", "type": ctype,
                   "daily_budget": budget, "asin": row["asin"],
                   "keywords": targets["keyword"].tolist()}
        res = client().create_campaign(payload)
        db.add_task(f"Launch campaign: {payload['name']}",
                    f"Auto-built at AED {budget}/day with {len(payload['keywords'])} targets.",
                    module="Advertising", priority="medium")
        st.success(f"Campaign draft built ({res['status']}). Task added to launch it.")


def _optimization() -> None:
    st.markdown(section_label("🎯 Ad Optimization — bids & targets"), unsafe_allow_html=True)
    listings = client().get_my_listings()
    item = st.selectbox("Item", listings["title"].tolist(), key="opt_item")
    targets = client().get_keyword_targets(item)
    styled_table(targets, highlight={
        "row-good": lambda r: r["action"] == "Raise",
        "row-warn": lambda r: r["action"] == "Lower"},
        badge_cols={"action": {"Raise": ("↑ Raise", "green"), "Hold": ("→ Hold", "blue"),
                               "Lower": ("↓ Lower", "amber")}})
    export_buttons(targets, "ad_targets")
    st.caption("Recommendation: raise bids on low-ACoS targets, lower on high-ACoS, "
               "and shift budget to the best-performing keywords per item.")


def render(nav=None) -> None:
    page_header("Advertising", "Campaigns, budget alarms, generation & bid optimization",
                icon="📢")
    ads = client().get_campaigns()
    _overview(ads)
    _budget_alarm(ads)
    t1, t2, t3 = st.tabs(["📈 Campaigns", "🧱 Generate", "🎯 Optimize"])
    with t1:
        _table(ads)
    with t2:
        _generator()
    with t3:
        _optimization()
