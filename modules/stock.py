"""
modules/stock.py
================
📦 Stock Management (Module 4).

  * Upload TWO files: Amazon inventory + Warehouse inventory.
  * Match items across both (SKU/ASIN/barcode, with fuzzy title fallback).
  * Apply per-brand / per-category min-stock rules from the Update Stock tab.
  * Output: Out-of-Stock / below-threshold list (table + Export) and fire
    notifications for out-of-stock items.

Sub-tab "Update Stock" persists min-stock thresholds to the DB.
"""

from __future__ import annotations
import re
import pandas as pd
import streamlit as st

from core import db, notifier, oskar_source
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


def _read_upload(f):
    """Read an uploaded CSV/Excel into a DataFrame (None if nothing uploaded)."""
    if f is None:
        return None
    return pd.read_csv(f) if f.name.lower().endswith(".csv") else pd.read_excel(f)


def _clean_flex_sku(value) -> str:
    """Base SKU = everything BEFORE the first '#'. Drops the '#' and anything after
    it (e.g. 'PWFC1029BWH#FBA1' → 'PWFC1029BWH', 'ABC#' → 'ABC')."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).split("#", 1)[0].strip()


def _find_sku_cols(df):
    """ALL SKU-type columns (Sku, Msku, Seller SKU, …) — anything whose header
    contains 'sku'. The '#FBA' suffix can live on any of them, so we clean them all."""
    return [c for c in df.columns if "sku" in re.sub(r"[^a-z0-9]", "", str(c).lower())]


def _connect_sku_col(sku_cols):
    """Which SKU column to look up on connect: prefer the MERCHANT SKU (Msku), since
    that's the product code connect knows — not Amazon's internal X00… SKU."""
    for c in sku_cols:
        n = re.sub(r"[^a-z0-9]", "", str(c).lower())
        if "msku" in n or "merchant" in n:
            return c
    return sku_cols[0] if sku_cols else None


def _find_sellable_col(df):
    """Locate the SELLABLE-stock column. Prefers an explicit 'sellable' header, then
    common Amazon/FBA names (afn-fulfillable-quantity, available, fulfillable)."""
    def norm(c):
        return re.sub(r"[^a-z0-9]", "", str(c).lower())
    cols = list(df.columns)
    for c in cols:                                   # explicit 'sellable'
        if "sellable" in norm(c):
            return c
    for key in ("afnfulfillablequantity", "fulfillablequantity", "fulfillable",
                "availablequantity", "quantityavailable", "available"):
        for c in cols:
            if key in norm(c):
                return c
    return None


def _flatten_scalars(d: dict, prefix: str = "") -> dict:
    """Flatten a connect record to columns: nested objects (e.g. 'product', 'media')
    are dotted (product.brand), lists become a '<key>_count'. Captures ALL the info
    connect returns without exploding huge lists like assets/images into the table."""
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten_scalars(v, prefix=key + "."))
        elif isinstance(v, list):
            out[f"{key}_count"] = len(v)
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[key] = v
    return out


def _update_stock_tab() -> None:
    st.markdown(section_label("Update Stock — Flex inventory + connect enrichment"),
                unsafe_allow_html=True)

    flex_file = st.file_uploader("Flex inventory (CSV/Excel)", type=["csv", "xlsx"],
                                 key="stk_flex")
    flex = _read_upload(flex_file)
    if flex is None:
        st.caption("Upload your Flex inventory Excel to begin.")
        return

    sku_cols = _find_sku_cols(flex)
    if not sku_cols:
        st.warning("Couldn't find a SKU column in the Flex file. Columns found: "
                   + ", ".join(map(str, flex.columns)))
        return

    # ── Clean EVERY SKU column: drop '#' and everything after it ──────────────
    out = flex.copy()
    total_rows = len(out)
    n_changed = 0
    for col in sku_cols:
        before = out[col].astype(str)
        out[col] = out[col].map(_clean_flex_sku)
        n_changed += int((before != out[col].astype(str)).sum())

    # ── Remove rows with 0 sellable stock ─────────────────────────────────────
    sell_col = _find_sellable_col(out)
    removed_zero = 0
    if sell_col is not None:
        qty = pd.to_numeric(out[sell_col], errors="coerce").fillna(0)
        removed_zero = int((qty <= 0).sum())
        out = out[qty > 0].copy()

    st.markdown(section_label("Flex inventory — cleaned"), unsafe_allow_html=True)
    msg = (f"Cleaned SKU column(s) **{', '.join(map(str, sku_cols))}** — removed '#' and "
           f"everything after it ({n_changed} cell(s) changed).")
    if sell_col is not None:
        msg += (f" Dropped **{removed_zero}** row(s) with 0 sellable stock "
                f"(column **{sell_col}**) — **{len(out)}** of {total_rows} rows kept.")
    st.caption(msg)
    if sell_col is None:
        st.warning("Couldn't find a 'sellable' stock column, so no 0-stock rows were "
                   "removed. Columns found: " + ", ".join(map(str, out.columns)))
    st.dataframe(out, use_container_width=True, hide_index=True)
    export_buttons(out, "flex_inventory_cleaned")
    st.session_state["flex_cleaned"] = out

    # ── Pull ALL info for each SKU from connect.oskarme.com ───────────────────
    st.markdown(section_label("Get all info from connect"), unsafe_allow_html=True)
    connect_col = _connect_sku_col(sku_cols)
    st.caption(f"Looking up connect by **{connect_col}** (merchant SKU).")
    skus = [s for s in dict.fromkeys(out[connect_col].astype(str).tolist()) if s.strip()]
    if db.get_setting("use_mock_oskar", "1") == "1":
        st.info("MOCK enrichment is ON (Settings → Connections → 'Use MOCK enrichment'). "
                "Turn it OFF to pull real connect.oskarme.com data.")
    if st.button(f"🔗 Get all info from connect for {len(skus)} SKU(s)",
                 use_container_width=True, type="primary"):
        rows, prog = [], st.progress(0.0)
        with st.spinner("Fetching product info from connect.oskarme.com…"):
            for i, sku in enumerate(skus):
                info = oskar_source.fetch_product_info(sku)
                row = {"SKU": sku, "Found": "✓" if info.get("ok") else "✗",
                       "Images": len(info.get("images") or [])}
                row.update(_flatten_scalars(info.get("data")))
                if not info.get("ok") and info.get("reason"):
                    row["Note"] = info["reason"]
                rows.append(row)
                prog.progress((i + 1) / max(len(skus), 1))
        st.session_state["flex_connect_info"] = pd.DataFrame(rows)
        st.rerun()

    enriched = st.session_state.get("flex_connect_info")
    if enriched is not None and not enriched.empty:
        found = int((enriched.get("Found") == "✓").sum()) if "Found" in enriched else 0
        st.caption(f"connect returned info for {found} of {len(enriched)} SKU(s).")
        st.dataframe(enriched, use_container_width=True, hide_index=True)
        export_buttons(enriched, "flex_connect_info")


def render(nav=None) -> None:
    page_header("Stock Management",
                "Match Amazon vs warehouse and surface every stock-out", icon="📦")
    t1, t2 = st.tabs(["🔍 Match & Out-of-Stock", "📝 Update Stock"])
    with t1:
        _match_tab()
    with t2:
        _update_stock_tab()
