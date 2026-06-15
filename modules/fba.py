"""
modules/fba.py
==============
🚚 FBA / Amazon Warehouse Optimization (Module 10).

Upload (or use mock) the items currently in Amazon's warehouse, then analyze:
  * RESEND — good sellers running low → units to resend (velocity × cover − on hand).
  * STUCK  — aged inventory with low velocity → recommend more ads or price cut.
"""

from __future__ import annotations
import math
import pandas as pd
import streamlit as st

from core import db
from core.api_client import client
from core.util import get_field
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge


def _analyze(df: pd.DataFrame, cover_days: int) -> pd.DataFrame:
    overrides = db.get_channel_overrides()  # FBA/FBM decisions from Hazmat
    rows = []
    for _, r in df.iterrows():
        vel = float(r["daily_velocity"])
        units = int(r["fba_units"])
        days_left = round(units / vel, 1) if vel else 999
        channel = overrides.get(r["sku"], "FBA")

        if channel == "FBM":
            # Merchant-fulfilled — never recommend an FBA resend for these.
            verdict, resend, action = "FBM", 0, "Merchant-fulfilled — exclude from FBA resend"
        else:
            stuck = vel < 0.4 and int(r["days_in_fba"]) > 60
            resend = max(math.ceil(vel * cover_days) - units, 0) if not stuck else 0
            verdict = "STUCK" if stuck else ("RESEND" if resend > 0 else "OK")
            action = ("More ads / price cut" if stuck else
                      ("Resend to FBA" if resend > 0 else "Hold"))

        rows.append({
            "sku": r["sku"], "title": r["title"], "channel": channel,
            "fba_units": units, "velocity/day": vel,
            "days_in_fba": int(r["days_in_fba"]), "days_left": days_left,
            "resend_units": resend, "verdict": verdict, "action": action,
        })
    return pd.DataFrame(rows)


def render(nav=None) -> None:
    page_header("FBA / Warehouse Optimization",
                "What to resend, and what's stuck and needs a push", icon="🚚")

    up = st.file_uploader("Amazon warehouse (FBA) inventory file (CSV/Excel)",
                          type=["csv", "xlsx"], key="fba_up")
    if up:
        raw = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
        df = pd.DataFrame({
            "sku": get_field(raw, "sku", ""), "title": get_field(raw, "title", ""),
            "fba_units": get_field(raw, "qty", 0),
            "daily_velocity": get_field(raw, "velocity", 0).fillna(0)
                if "velocity" in [c.lower() for c in raw.columns] else 0.5,
            "days_in_fba": 30})
        src = f"uploaded ({up.name})"
    else:
        df = client().get_fba_inventory()
        src = "mock FBA inventory (upload to override)"
    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)

    cover = st.slider("Target FBA cover (days)", 14, 90, 30)
    res = _analyze(df, cover)

    resend_n = int((res["verdict"] == "RESEND").sum())
    stuck_n = int((res["verdict"] == "STUCK").sum())
    fbm_n = int((res["verdict"] == "FBM").sum())
    kpi_row([
        {"label": "SKUs in FBA", "value": str(len(res)), "accent": "blue"},
        {"label": "To Resend", "value": str(resend_n), "accent": "emerald",
         "sub": f"{int(res['resend_units'].sum())} units total"},
        {"label": "Stuck", "value": str(stuck_n), "accent": "coral",
         "sub": "Aged + slow"},
        {"label": "FBM (excluded)", "value": str(fbm_n), "accent": "violet",
         "sub": "Merchant-fulfilled"},
    ])
    if fbm_n:
        st.caption(f"{fbm_n} item(s) marked FBM in Hazmat are excluded from FBA resend.")
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown(section_label("FBA Analysis"), unsafe_allow_html=True)
    styled_table(res, highlight={
        "row-danger": lambda r: r["verdict"] == "STUCK",
        "row-good": lambda r: r["verdict"] == "RESEND",
        "row-warn": lambda r: r["verdict"] == "FBM"},
        badge_cols={"verdict": {"STUCK": ("STUCK", "coral"), "RESEND": ("RESEND", "green"),
                                "OK": ("OK", "blue"), "FBM": ("FBM (skip)", "violet")},
                    "channel": {"FBA": ("FBA", "blue"), "FBM": ("FBM", "violet")}})
    export_buttons(res, "fba_optimization")

    if st.button("➕ Add FBA actions to Tasks"):
        for _, r in res[res["verdict"].isin(["RESEND", "STUCK"])].iterrows():
            db.add_task(f"{r['verdict']}: {r['title']}",
                        (f"Resend {r['resend_units']} units." if r["verdict"] == "RESEND"
                         else f"Stuck {r['days_in_fba']}d — {r['action']}."),
                        module="FBA / Warehouse Optimization",
                        priority="high" if r["verdict"] == "STUCK" else "medium",
                        related_id=r["sku"])
        st.success("FBA tasks added.")
