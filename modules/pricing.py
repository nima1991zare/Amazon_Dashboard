"""
modules/pricing.py
==================
💰 Pricing (Module 5).

Tabs:
  1. Calculator   — manual fee components → min price + price at target profit %.
                    (api_client.get_fees_estimate stub to auto-pull fees later.)
  2. Lost Buybox  — items that lost the buybox on price (api_client; mock), Export,
                    notify.
  3. Market Tracker — set a competitive price for an item. Manual mode (paste your
                    URL + competitor URLs) or Auto mode (suggest best price from
                    feature potential). Fetches Noon/other UAE prices, stores price
                    history in DB, charts it.
"""

from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, notifier, mock_data
from core.api_client import client
from core.components import styled_table, export_buttons, page_header
from core.styles import section_label, glow_block, badge, alert, PALETTE


def _calculator() -> None:
    st.markdown(section_label("🧮 Pricing Calculator"), unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        cost = st.number_input("Product cost (AED)", 0.0, value=180.0, step=5.0)
        referral_pct = st.slider("Referral fee %", 5, 20, 15)
    with c2:
        fba = st.number_input("FBA fee (AED)", 0.0, value=14.0, step=1.0)
        shipping = st.number_input("Inbound shipping (AED)", 0.0, value=6.0, step=1.0)
    with c3:
        vat_pct = st.slider("VAT %", 0, 10, 5)
        target_profit = st.slider("Target profit %", 5, 60, 25)

    # Min price: covers cost+fba+shipping+referral+vat with zero profit.
    # P*(1 - referral - vat) = cost+fba+shipping  →  P_min
    denom_min = 1 - referral_pct / 100 - vat_pct / 100
    denom_tgt = 1 - referral_pct / 100 - vat_pct / 100 - target_profit / 100

    fixed = cost + fba + shipping
    if denom_min <= 0 or denom_tgt <= 0:
        st.markdown(alert("Fee percentages too high — no feasible price.", kind="coral",
                          icon="⛔"), unsafe_allow_html=True)
        return
    min_price = fixed / denom_min
    target_price = fixed / denom_tgt

    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown(glow_block(f"AED {min_price:,.2f}", "Minimum Price (break-even)"),
                    unsafe_allow_html=True)
    with cc2:
        st.markdown(glow_block(f"AED {target_price:,.2f}", f"Price @ {target_profit}% profit"),
                    unsafe_allow_html=True)
    st.caption("TODO(api_client.get_fees_estimate): auto-pull referral & FBA fees by ASIN.")


def _lost_buybox() -> None:
    st.markdown(section_label("🏷️ Lost Buybox"), unsafe_allow_html=True)
    df = client().get_lost_buybox()
    df = df.copy()
    df["gap"] = (df["your_price"] - df["buybox_price"]).round(2)
    styled_table(df, highlight={"row-danger": lambda r: True})
    export_buttons(df, "lost_buybox")
    cols = st.columns([1, 1, 2])
    with cols[0]:
        if st.button("➕ Add to Tasks", key="lb_task"):
            for _, r in df.iterrows():
                db.add_task(f"Recover buybox: {r['title']}",
                            f"Competitor at AED {r['buybox_price']} vs your AED {r['your_price']}.",
                            module="Pricing", priority="high", related_id=r["sku"])
            st.success("Tasks added.")
    with cols[1]:
        if st.button("🔔 Notify", key="lb_notify"):
            res = notifier.notify_event("lost_buybox", "Lost buybox alert",
                                        f"{len(df)} items lost the buybox on price.")
            for ch, ok, msg in res:
                (st.success if ok else st.warning)(f"{ch}: {msg}")


def _market_tracker() -> None:
    st.markdown(section_label("🛰️ Market Tracker"), unsafe_allow_html=True)
    listings = client().get_my_listings()
    item = st.selectbox("Item", listings["title"].tolist())
    mode = st.radio("Mode", ["Manual (paste URLs)", "Auto (suggest best price)"],
                    horizontal=True)

    if mode.startswith("Manual"):
        st.text_input("Your item URL", placeholder="https://www.amazon.ae/dp/...")
        st.text_area("Competitor URLs (Amazon / Noon / other UAE, one per line)",
                     placeholder="https://www.noon.com/...\nhttps://www.sharafdg.com/...",
                     height=90)

    if st.button("📡 Fetch competitor prices"):
        comp = mock_data.competitor_prices(item)
        # Persist a price-history snapshot for each source.
        for _, r in comp.iterrows():
            db.add_price(item_id=item, item_name=item, source=r["source"], price=r["price"])
        st.session_state["last_comp"] = comp.to_dict("records")

    comp = st.session_state.get("last_comp")
    if comp:
        cdf = pd.DataFrame(comp)
        lowest = cdf["price"].min()
        your_price = float(listings[listings["title"] == item]["price"].iloc[0])
        st.markdown(badge(f"Lowest market: AED {lowest:,.0f}", "amber") + " " +
                    badge(f"Your price: AED {your_price:,.0f}",
                          "coral" if your_price > lowest else "green"),
                    unsafe_allow_html=True)
        styled_table(cdf, highlight={"row-good": lambda r: r["price"] == lowest})
        export_buttons(cdf, "competitor_prices")

        if mode.startswith("Auto"):
            # Simple feature-potential suggestion: match-but-not-undercut to protect margin.
            suggested = round(max(lowest - 1, your_price * 0.97), 2)
            st.markdown(glow_block(f"AED {suggested:,.2f}", "Suggested competitive price"),
                        unsafe_allow_html=True)

    # Price history chart.
    hist = db.get_price_history(item)
    if hist:
        st.markdown(section_label("📈 Price History"), unsafe_allow_html=True)
        hdf = pd.DataFrame(hist)
        fig = go.Figure()
        for source, grp in hdf.groupby("source"):
            fig.add_trace(go.Scatter(x=grp["captured_at"], y=grp["price"],
                                     mode="lines+markers", name=source))
        fig.update_layout(template="plotly_dark", height=320,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=10, r=10, t=10, b=10),
                          legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)


def render(nav=None) -> None:
    page_header("Pricing", "Calculate floors, recover buyboxes, track the market",
                icon="💰")
    t1, t2, t3 = st.tabs(["🧮 Calculator", "🏷️ Lost Buybox", "🛰️ Market Tracker"])
    with t1:
        _calculator()
    with t2:
        _lost_buybox()
    with t3:
        _market_tracker()
