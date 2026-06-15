"""
modules/hazmat_inactive.py
==========================
☣️ Hazmat & Inactive (new module). Two parts:

PART 1 — HAZMAT (FBA Dangerous Goods compliance)
  Monitors the FBA Compliance Dashboard (via api_client; mock now, real API later
  — sellercentral.amazon.ae/fba/compliance-dashboard). Maps each item's status:
    * "Unable to classify"            -> generate a Battery Exemption sheet and
                                         upload it (button generates an upload-ready
                                         .xlsx using Amazon's exact template).
    * "Dangerous Good FBA Fulfillable"-> APPROVED -> set fulfilment channel to FBA.
    * "Dangerous Good Unfulfillable"  -> NOT approved -> set fulfilment channel FBM.
  Actions call api_client stubs and log tasks.

PART 2 — INACTIVE
  Lists inactive listings with the reason, Export, and one-click tasks to fix.

You can also upload the dashboard's own export (CSV/Excel) instead of mock data.
"""

from __future__ import annotations
import io
import pandas as pd
import streamlit as st

from core import db, mock_data
from core.api_client import client
from core.util import get_field
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge, alert


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------
def _hazmat_bucket(status: str) -> str:
    s = str(status).strip().lower()
    if "unable" in s:
        return "unable"
    if "unfulfil" in s:          # unfulfillable (check before fulfillable!)
        return "unfulfillable"
    if "fulfil" in s:
        return "fulfillable"
    return "other"


_ACTION = {
    "unable":        "Generate & upload hazmat exemption sheet",
    "fulfillable":   "Approved → set fulfilment channel to FBA",
    "unfulfillable": "Not approved → set fulfilment channel to FBM",
    "other":         "Review manually",
}
_BADGE = {
    "unable": ("⚠ Unable to classify", "amber"),
    "fulfillable": ("✓ FBA Fulfillable (approved)", "green"),
    "unfulfillable": ("✗ Unfulfillable", "coral"),
    "other": ("Review", "violet"),
}


# ---------------------------------------------------------------------------
# Battery exemption sheet generator (Amazon's exact template + dropdowns)
# ---------------------------------------------------------------------------
def build_battery_exemption_xlsx(items: pd.DataFrame) -> bytes:
    """Return an upload-ready .xlsx pre-filled with ASIN + title for the given
    items, with Amazon's exact headers and data-validation dropdowns on the
    battery columns. The remaining cells are left for the user/operator to fill.
    """
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Battery exemption sheet"
    ws.append(mock_data.HAZMAT_TEMPLATE_HEADERS)
    for _, r in items.iterrows():
        ws.append([r.get("asin", ""), r.get("title", ""), "", "", "", "", "", "", "", ""])

    # Hidden sheet holding the allowed dropdown values.
    lists = wb.create_sheet("Lists")
    a = mock_data.HAZMAT_ALLOWED
    columns = {"A": a["sold"], "B": a["chemical"], "C": a["packaging"],
               "D": a["cells"], "E": a["watt_hours"], "F": a["spillability"]}
    for col, vals in columns.items():
        for i, v in enumerate(vals, start=1):
            lists[f"{col}{i}"] = v
    lists.sheet_state = "hidden"

    last_row = ws.max_row + 100  # allow extra manual rows
    # (sheet column letter, lists column, value count)
    dv_map = [("D", "A", len(a["sold"])), ("E", "B", len(a["chemical"])),
              ("F", "C", len(a["packaging"])), ("G", "D", len(a["cells"])),
              ("H", "E", len(a["watt_hours"])), ("I", "F", len(a["spillability"]))]
    for sheet_col, list_col, n in dv_map:
        dv = DataValidation(type="list",
                            formula1=f"Lists!${list_col}$1:${list_col}${n}",
                            allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{sheet_col}2:{sheet_col}{last_row}")

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ---------------------------------------------------------------------------
# PART 1 — Hazmat
# ---------------------------------------------------------------------------
def _hazmat_tab() -> None:
    st.markdown(
        "<p style='color:var(--muted); font-size:.86rem'>Monitors the "
        "<b>FBA Compliance Dashboard</b>. Live API will connect here once credentials "
        "are added (Settings → Amazon API). For now it uses sample data — or upload the "
        "dashboard export below.</p>", unsafe_allow_html=True)

    up = st.file_uploader("Upload compliance dashboard export (CSV/Excel) — optional",
                          type=["csv", "xlsx"], key="hz_up")
    if up:
        raw = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
        df = pd.DataFrame({
            "asin": get_field(raw, "asin", "").astype(str),
            "sku": get_field(raw, "sku", "").astype(str),
            "title": get_field(raw, "title", "").astype(str),
            "hazmat_status": get_field(raw, "category", "").astype(str)
                if "status" not in [c.lower() for c in raw.columns] else raw[
                    [c for c in raw.columns if c.lower() == "status"][0]].astype(str),
            "fulfilment_channel": get_field(raw, "category", "FBM"),
        })
        src = f"uploaded ({up.name})"
    else:
        df = client().get_hazmat_compliance()
        src = "sample data (upload to override)"
    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)

    df = df.copy()
    df["bucket"] = df["hazmat_status"].map(_hazmat_bucket)
    df["action"] = df["bucket"].map(_ACTION)
    # Reflect any channel decisions already made (persisted) so the column updates.
    overrides = db.get_channel_overrides()
    df["fulfilment_channel"] = df.apply(
        lambda r: overrides.get(r["sku"], r["fulfilment_channel"]), axis=1)

    n_unable = int((df["bucket"] == "unable").sum())
    n_fba = int((df["bucket"] == "fulfillable").sum())
    n_fbm = int((df["bucket"] == "unfulfillable").sum())
    kpi_row([
        {"label": "Unable to classify", "value": str(n_unable), "accent": "amber",
         "sub": "Need exemption sheet"},
        {"label": "FBA Fulfillable", "value": str(n_fba), "accent": "emerald",
         "sub": "Approved → FBA"},
        {"label": "Unfulfillable", "value": str(n_fbm), "accent": "coral",
         "sub": "→ switch to FBM"},
    ])
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Main table.
    show = df[["asin", "sku", "title", "hazmat_status", "fulfilment_channel", "action"]].copy()
    show["hazmat_status"] = df["bucket"].map(lambda b: _BADGE[b][0])
    styled_table(
        show,
        highlight={"row-danger": lambda r: "Unfulfillable" in r["hazmat_status"],
                   "row-warn": lambda r: "Unable" in r["hazmat_status"],
                   "row-good": lambda r: "Fulfillable" in r["hazmat_status"]},
        badge_cols={"hazmat_status": {v[0]: v for v in _BADGE.values()}})
    export_buttons(df.drop(columns=["bucket"]), "hazmat_compliance")

    # --- Unable to classify → generate exemption sheet --------------------
    st.markdown(section_label("⚠ Unable to classify → generate exemption sheet"),
                unsafe_allow_html=True)
    unable = df[df["bucket"] == "unable"]
    if unable.empty:
        st.caption("No 'unable to classify' items right now.")
    else:
        st.markdown(f"<p style='color:var(--muted)'>{len(unable)} item(s) need a Battery "
                    f"Exemption sheet generated and uploaded.</p>", unsafe_allow_html=True)
        styled_table(unable[["asin", "sku", "title"]])
        xlsx = build_battery_exemption_xlsx(unable)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📄 Generate Battery Exemption Sheet (.xlsx)", xlsx,
                               file_name="battery_exemption_sheet.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True, key="hz_gen")
        with c2:
            if st.button("⬆ Upload to Amazon (API)", use_container_width=True):
                res = client().upload_hazmat_file(xlsx, "battery_exemption_sheet.xlsx")
                if res.get("status") == "mock_ok":
                    st.info("Mock upload OK. Wire the real compliance API in "
                            "api_client.upload_hazmat_file().")
                for _, r in unable.iterrows():
                    db.add_task(f"Hazmat: submit exemption for {r['title']}",
                                "Generated battery exemption sheet — upload to compliance dashboard.",
                                module="Hazmat & Inactive", priority="high", related_id=r["sku"])
                st.success("Tasks logged for exemption submission.")
        st.caption("The sheet uses Amazon's exact template headers + dropdowns. Fill the "
                   "battery details, then upload (auto-upload connects via API later).")

    # --- Channel switches -------------------------------------------------
    st.markdown(section_label("🔁 Fulfilment channel actions"), unsafe_allow_html=True)
    cc1, cc2 = st.columns(2)
    with cc1:
        fba_items = df[df["bucket"] == "fulfillable"]
        st.markdown(badge(f"{len(fba_items)} approved → FBA", "green"), unsafe_allow_html=True)
        if st.button("Set approved items to FBA", use_container_width=True,
                     disabled=fba_items.empty):
            for _, r in fba_items.iterrows():
                client().set_fulfilment_channel(r["sku"], "FBA")   # API stub
                db.set_channel_override(r["sku"], "FBA")           # persist locally
                db.add_task(f"Switch to FBA: {r['title']}",
                            "Approved as FBA Fulfillable dangerous good.",
                            module="Hazmat & Inactive", priority="medium", related_id=r["sku"])
            st.success(f"Set {len(fba_items)} item(s) to FBA. Reflected in Stock & "
                       f"Inventory views; tasks logged.")
            st.rerun()
    with cc2:
        fbm_items = df[df["bucket"] == "unfulfillable"]
        st.markdown(badge(f"{len(fbm_items)} unfulfillable → FBM", "coral"), unsafe_allow_html=True)
        if st.button("Set unfulfillable items to FBM", use_container_width=True,
                     disabled=fbm_items.empty):
            for _, r in fbm_items.iterrows():
                client().set_fulfilment_channel(r["sku"], "FBM")   # API stub
                db.set_channel_override(r["sku"], "FBM")           # persist locally
                db.add_task(f"Switch to FBM: {r['title']}",
                            "Dangerous good unfulfillable by FBA — move to merchant fulfilment.",
                            module="Hazmat & Inactive", priority="high", related_id=r["sku"])
            st.success(f"Set {len(fbm_items)} item(s) to FBM. Reflected in Stock & "
                       f"Inventory views; tasks logged.")
            st.rerun()


# ---------------------------------------------------------------------------
# PART 2 — Inactive
# ---------------------------------------------------------------------------
def _inactive_tab() -> None:
    up = st.file_uploader("Upload inactive listings export (CSV/Excel) — optional",
                          type=["csv", "xlsx"], key="inact_up")
    if up:
        raw = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
        df = pd.DataFrame({
            "asin": get_field(raw, "asin", ""), "sku": get_field(raw, "sku", ""),
            "title": get_field(raw, "title", ""), "status": "Inactive",
            "reason": get_field(raw, "category", "Unknown"),
            "last_active": get_field(raw, "category", ""),
        })
        src = f"uploaded ({up.name})"
    else:
        df = client().get_inactive_listings()
        src = "sample data (upload to override)"
    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)

    kpi_row([
        {"label": "Inactive listings", "value": str(len(df)), "accent": "coral"},
        {"label": "Out of stock",
         "value": str(int(df["reason"].str.contains("stock", case=False, na=False).sum())),
         "accent": "amber"},
        {"label": "Suppressed",
         "value": str(int(df["reason"].str.contains("suppress", case=False, na=False).sum())),
         "accent": "violet"},
    ])
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    st.markdown(section_label("Inactive Listings"), unsafe_allow_html=True)
    styled_table(df, highlight={"row-danger": lambda r: True})
    export_buttons(df, "inactive_listings")

    if st.button("➕ Add reactivation tasks"):
        for _, r in df.iterrows():
            db.add_task(f"Reactivate: {r['title']}", f"Inactive — {r['reason']}.",
                        module="Hazmat & Inactive", priority="medium", related_id=r["sku"])
        st.success("Reactivation tasks added.")


def render(nav=None) -> None:
    page_header("Hazmat & Inactive",
                "Dangerous-goods compliance and inactive-listing recovery", icon="☣️")
    t1, t2 = st.tabs(["☣️ Hazmat (Dangerous Goods)", "💤 Inactive"])
    with t1:
        _hazmat_tab()
    with t2:
        _inactive_tab()
