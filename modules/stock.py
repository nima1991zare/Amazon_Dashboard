"""
modules/stock.py
================
📦 Stock Management (Module 4).

  * Upload TWO files: Amazon inventory + Warehouse inventory.
  * Match items across both (SKU/ASIN/barcode, with fuzzy title fallback).
  * Apply per-brand / per-category min-stock rules from Stock Configuration.
  * Output: Out-of-Stock / below-threshold list (table + Export) and fire
    notifications for out-of-stock items.

Sub-tab "Stock Configuration" persists thresholds to the DB.
"""

from __future__ import annotations
import pandas as pd
import streamlit as st

from core import db, notifier
from core.util import get_field, fuzzy_match_key
from core.components import styled_table, export_buttons, page_header
from core.styles import section_label, badge, alert


def _normalize(df: pd.DataFrame, qty_default=0) -> pd.DataFrame:
    return pd.DataFrame({
        "sku": get_field(df, "sku", "").astype(str),
        "asin": get_field(df, "asin", "").astype(str),
        "barcode": get_field(df, "barcode", "").astype(str),
        "title": get_field(df, "title", "").astype(str),
        "brand": get_field(df, "brand", "").astype(str),
        "category": get_field(df, "category", "").astype(str),
        "qty": pd.to_numeric(get_field(df, "qty", qty_default), errors="coerce").fillna(0),
    })


def _match(amazon: pd.DataFrame, warehouse: pd.DataFrame) -> pd.DataFrame:
    """Match Amazon rows to warehouse rows by SKU→ASIN→barcode→fuzzy title."""
    overrides = db.get_channel_overrides()  # FBA/FBM decisions from Hazmat
    wh_by_sku = {r["sku"]: r for _, r in warehouse.iterrows() if r["sku"]}
    wh_by_asin = {r["asin"]: r for _, r in warehouse.iterrows() if r["asin"]}
    wh_by_bc = {r["barcode"]: r for _, r in warehouse.iterrows() if r["barcode"]}
    wh_titles = warehouse["title"].tolist()

    rows = []
    for _, a in amazon.iterrows():
        match = None
        if a["sku"] in wh_by_sku:
            match = wh_by_sku[a["sku"]]
        elif a["asin"] in wh_by_asin:
            match = wh_by_asin[a["asin"]]
        elif a["barcode"] in wh_by_bc:
            match = wh_by_bc[a["barcode"]]
        else:
            ft = fuzzy_match_key(a["title"], wh_titles)
            if ft is not None:
                match = warehouse[warehouse["title"] == ft].iloc[0]

        wh_qty = int(match["qty"]) if match is not None else 0
        brand = a["brand"] or (match["brand"] if match is not None else "")
        category = a["category"] or (match["category"] if match is not None else "")
        threshold = db.stock_threshold_for(brand, category)
        rows.append({
            "sku": a["sku"], "title": a["title"], "brand": brand, "category": category,
            "channel": overrides.get(a["sku"], "FBA"),
            "amazon_qty": int(a["qty"]), "warehouse_qty": wh_qty,
            "threshold": threshold,
            "status": "OUT OF STOCK" if a["qty"] == 0 else
                      ("LOW" if a["qty"] < threshold else "OK"),
        })
    return pd.DataFrame(rows)


def _match_tab() -> None:
    c1, c2 = st.columns(2)
    with c1:
        amz_file = st.file_uploader("Amazon inventory file (CSV/Excel)",
                                    type=["csv", "xlsx"], key="stk_amz")
    with c2:
        wh_file = st.file_uploader("Warehouse inventory file (CSV/Excel)",
                                   type=["csv", "xlsx"], key="stk_wh")

    if amz_file:
        amazon = pd.read_csv(amz_file) if amz_file.name.endswith(".csv") else pd.read_excel(amz_file)
    else:
        from core.api_client import client
        amazon = client().get_my_listings().rename(columns={"fba_stock": "qty"})
    if wh_file:
        warehouse = pd.read_csv(wh_file) if wh_file.name.endswith(".csv") else pd.read_excel(wh_file)
    else:
        from core import mock_data
        warehouse = mock_data.inventory_website_items().rename(columns={"warehouse_qty": "qty"})

    src = "uploaded files" if (amz_file and wh_file) else "sample data (upload to override)"
    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)

    matched = _match(_normalize(amazon), _normalize(warehouse))
    oos = matched[matched["status"] != "OK"]

    st.markdown(section_label("Out-of-Stock & Low-Stock Items"), unsafe_allow_html=True)
    if oos.empty:
        st.markdown(alert("All matched items are above threshold.", kind="green", icon="✅"),
                    unsafe_allow_html=True)
    else:
        styled_table(oos, highlight={
            "row-danger": lambda r: r["status"] == "OUT OF STOCK",
            "row-warn": lambda r: r["status"] == "LOW"},
            badge_cols={"status": {"OUT OF STOCK": ("OUT OF STOCK", "coral"),
                                   "LOW": ("LOW", "amber")},
                        "channel": {"FBA": ("FBA", "blue"), "FBM": ("FBM", "violet")}})
        export_buttons(oos, "out_of_stock")

        cta = st.columns([1, 1, 2])
        with cta[0]:
            if st.button("➕ Add to Tasks"):
                for _, r in oos.iterrows():
                    db.add_task(f"Restock: {r['title']} ({r['status']})",
                                f"Amazon {r['amazon_qty']} vs threshold {r['threshold']}; "
                                f"warehouse has {r['warehouse_qty']}.",
                                module="Stock Management",
                                priority="high" if r["status"] == "OUT OF STOCK" else "medium",
                                related_id=r["sku"])
                st.success("Tasks added.")
        with cta[1]:
            if st.button("🔔 Notify"):
                names = ", ".join(oos[oos["status"] == "OUT OF STOCK"]["title"].tolist())
                res = notifier.notify_event("out_of_stock", "Out of stock alert",
                                            f"Out of stock: {names or 'none'}")
                for ch, ok, msg in res:
                    (st.success if ok else st.warning)(f"{ch}: {msg}")


def _config_tab() -> None:
    st.markdown(section_label("Stock Configuration — min thresholds"), unsafe_allow_html=True)
    st.caption("Brand rule overrides category rule, which overrides the global default (10).")

    c1, c2, c3, c4 = st.columns([1.2, 2, 1, 1])
    scope = c1.selectbox("Scope", ["brand", "category"])
    value = c2.text_input("Value (e.g. Apple / Audio)")
    minv = c3.number_input("Min stock", min_value=0, value=15)
    with c4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("💾 Save rule", use_container_width=True) and value:
            db.set_stock_rule(scope, value, int(minv))
            st.success(f"Saved {scope} rule: {value} ≥ {minv}")
            st.rerun()

    rules = db.get_stock_rules()
    if rules:
        styled_table(pd.DataFrame(rules)[["scope_type", "scope_value", "min_stock"]])
    else:
        st.caption("No custom rules yet — global default of 10 applies.")


def render(nav=None) -> None:
    page_header("Stock Management",
                "Match Amazon vs warehouse and surface every stock-out", icon="📦")
    t1, t2 = st.tabs(["🔍 Match & Out-of-Stock", "⚙️ Stock Configuration"])
    with t1:
        _match_tab()
    with t2:
        _config_tab()
