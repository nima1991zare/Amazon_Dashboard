"""
modules/assets.py
=================
🎨 Asset Management (Module 9).

  * Suggests A+ content per item and shows ready A+ content synced from a sheet
    (mock via api/inventory source).
  * Pulls published video links (from inventory website / sheet) and shows
    per-item status: Uploaded (green) / Not Uploaded (amber).
"""

from __future__ import annotations
import streamlit as st

from core import db, inventory_source, mock_data
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge


def render(nav=None) -> None:
    page_header("Asset Management", "A+ content suggestions and video upload status",
                icon="🎨")

    df = mock_data.asset_status().copy()
    videos = inventory_source.fetch_video_links()  # mock pulls from same source

    uploaded = int((df["video_status"] == "Uploaded").sum())
    aplus_ready = int((df["aplus_status"] == "Ready").sum())
    kpi_row([
        {"label": "Items", "value": str(len(df)), "accent": "blue"},
        {"label": "A+ Ready", "value": str(aplus_ready), "accent": "emerald"},
        {"label": "Videos Uploaded", "value": f"{uploaded}/{len(df)}", "accent": "violet"},
        {"label": "Videos Pending", "value": str(len(df) - uploaded), "accent": "amber"},
    ])
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown(section_label("A+ Content & Video Status"), unsafe_allow_html=True)
    styled_table(df, highlight={
        "row-good": lambda r: r["video_status"] == "Uploaded",
        "row-warn": lambda r: r["video_status"] == "Not Uploaded"},
        badge_cols={
            "aplus_status": {"Ready": ("✓ Ready", "green"), "Draft": ("Draft", "amber"),
                             "Suggested": ("Suggested", "violet")},
            "video_status": {"Uploaded": ("✓ Uploaded", "green"),
                             "Not Uploaded": ("⏳ Not Uploaded", "amber")}})
    export_buttons(df, "asset_status")

    st.markdown(section_label("Suggested A+ Modules"), unsafe_allow_html=True)
    for _, r in df[df["aplus_status"] != "Ready"].iterrows():
        st.markdown(
            f"<div class='glass-card' style='margin-bottom:8px; padding:13px 16px'>"
            f"<b>{r['item']}</b> — suggest: comparison chart, lifestyle banner, "
            f"feature callouts, brand story. {badge('Create A+', 'blue')}</div>",
            unsafe_allow_html=True)

    if st.button("➕ Add asset tasks"):
        for _, r in df[(df["aplus_status"] != "Ready") | (df["video_status"] == "Not Uploaded")].iterrows():
            db.add_task(f"Produce assets: {r['item']}",
                        f"A+ {r['aplus_status']}, video {r['video_status']}.",
                        module="Asset Management", priority="low", related_id=r["item"])
        st.success("Asset tasks added.")
