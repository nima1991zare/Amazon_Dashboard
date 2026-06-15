"""
modules/home.py
===============
🏠 Home — Daily Action Center.

Aggregates the most important signals from every module into headline KPI cards
and a single prioritized task feed (read from the central Tasks table). Each task
row has a "Go" button that navigates to its related section.

regenerate_tasks() scans all modules' (mock) data + e-commerce best practices and
writes tasks into the DB; it runs once per session and can be re-run on demand.
"""

from __future__ import annotations
import streamlit as st

from core import db
from core.api_client import client
from core.components import kpi_row, page_header
from core.styles import headline, alert, section_label


def regenerate_tasks() -> None:
    """Scan all data sources and (re)populate the central Tasks table."""
    db.clear_tasks()
    api = client()
    listings = api.get_my_listings()
    campaigns = api.get_campaigns()
    buybox = api.get_lost_buybox()
    market = api.get_market_comparison()
    events = api.get_events()
    catalog_skus = db.get_catalog_skus()

    # Out of stock
    for _, r in listings[listings["fba_stock"] == 0].iterrows():
        db.add_task(f"Restock OUT-OF-STOCK: {r['title']}",
                    f"Selling {r['daily_velocity']}/day with 0 units.",
                    module="Stock Management", priority="high", related_id=r["sku"])
    # Below threshold
    for _, r in listings[(listings["fba_stock"] > 0) &
                         (listings["fba_stock"] < listings["daily_velocity"] * 10)].iterrows():
        db.add_task(f"Low stock: {r['title']}",
                    f"{r['fba_stock']} units left (~{r['fba_stock']/max(r['daily_velocity'],0.1):.0f} days).",
                    module="Stock Management", priority="medium", related_id=r["sku"])
    # Lost buybox
    for _, r in buybox.iterrows():
        db.add_task(f"Lost buybox: {r['title']}",
                    f"Competitor {r['buybox_winner']} at AED {r['buybox_price']} vs your AED {r['your_price']}.",
                    module="Pricing", priority="high", related_id=r["sku"])
    # Over budget campaigns
    for _, r in campaigns[campaigns["spend_today"] > campaigns["avg_daily"] * 1.2].iterrows():
        db.add_task(f"Campaign over budget: {r['campaign']}",
                    f"AED {r['spend_today']} vs AED {r['avg_daily']} avg.",
                    module="Advertising", priority="medium", related_id=r["campaign"])
    # Trending + well priced → promote
    for _, r in market[market["signal"].isin(["Trending", "Hidden Gem"])].iterrows():
        db.add_task(f"Promote trending item: {r['item']}",
                    f"{r['signal']} with {r['monthly_demand']:,} monthly demand — add A+ content & ads.",
                    module="Market Analysis", priority="medium", related_id=r["item"])
    # New arrivals to list (warehouse items not in catalog handled in intake;
    # here we surface the count as a task)
    from core import inventory_source
    inv, _ = inventory_source.fetch_inventory()
    if not inv.empty:
        new_n = int((~inv["sku"].isin(catalog_skus)).sum())
        if new_n:
            db.add_task(f"List {new_n} new arrivals on Amazon",
                        "New warehouse items not yet in your catalog.",
                        module="Inventory & Listing Intake", priority="high")
    # Upcoming events
    for _, r in events.head(2).iterrows():
        db.add_task(f"Prepare for event: {r['event']} ({r['date']})",
                    r["action"], module="Event Planner", priority="low")


def render(nav) -> None:
    page_header("Daily Action Center",
                "Everything that needs your attention today, in priority order", icon="🏠")

    # Regenerate once per session unless asked.
    if "tasks_seeded" not in st.session_state:
        regenerate_tasks()
        st.session_state["tasks_seeded"] = True

    api = client()
    listings = api.get_my_listings()
    campaigns = api.get_campaigns()
    buybox = api.get_lost_buybox()
    from core import inventory_source
    inv, _ = inventory_source.fetch_inventory()
    new_to_list = int((~inv["sku"].isin(db.get_catalog_skus())).sum()) if not inv.empty else 0

    kpi_row([
        {"label": "Items to List", "value": str(new_to_list), "accent": "emerald",
         "sub": "New arrivals pending"},
        {"label": "Out of Stock", "value": str(int((listings["fba_stock"] == 0).sum())),
         "accent": "coral", "sub": "Live ASINs at zero"},
        {"label": "Lost Buyboxes", "value": str(len(buybox)), "accent": "coral",
         "sub": "Due to competitor price"},
        {"label": "Campaigns Over Budget",
         "value": str(int((campaigns["spend_today"] > campaigns["avg_daily"] * 1.2).sum())),
         "accent": "violet", "sub": ">20% above daily avg"},
    ])

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    top = st.columns([3, 1])
    with top[0]:
        st.markdown(section_label("⚡ Prioritized Task Feed"), unsafe_allow_html=True)
    with top[1]:
        if st.button("🔄 Rescan", use_container_width=True):
            regenerate_tasks()
            st.rerun()

    tasks = db.get_tasks("open")
    if not tasks:
        st.markdown(alert("All clear — no open tasks.", kind="green", icon="✅"),
                    unsafe_allow_html=True)
        return

    accent_map = {"high": "coral", "medium": "amber", "low": "blue"}
    icon_map = {"high": "🔴", "medium": "🟠", "low": "🔵"}
    for t in tasks:
        c1, c2, c3 = st.columns([6, 1.4, 1])
        with c1:
            st.markdown(
                headline(t["title"], t["detail"],
                         accent=accent_map.get(t["priority"], "blue"),
                         icon=icon_map.get(t["priority"], "•")),
                unsafe_allow_html=True)
        with c2:
            if t["module"] and st.button(f"↪ {t['module'].split()[0]}", key=f"go_{t['id']}",
                                         use_container_width=True):
                nav(t["module"])
        with c3:
            if st.button("✓ Done", key=f"done_{t['id']}", use_container_width=True):
                db.complete_task(t["id"])
                st.rerun()
