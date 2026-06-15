"""
modules/events.py
=================
📅 Event Planner (Module 11).

Fetches Amazon retail events (api_client; mock), shows them as date-ordered
cards, and surfaces upcoming events as tasks on Home.
"""

from __future__ import annotations
import pandas as pd
import streamlit as st

from core import db
from core.api_client import client
from core.components import styled_table, export_buttons, page_header
from core.styles import section_label, badge


def render(nav=None) -> None:
    page_header("Event Planner", "Amazon.ae retail calendar and prep actions", icon="📅")
    df = client().get_events().copy().sort_values("date")

    st.markdown(section_label("Upcoming Events"), unsafe_allow_html=True)
    for _, r in df.iterrows():
        st.markdown(
            f"<div class='glass-card' style='margin-bottom:10px; display:flex; "
            f"justify-content:space-between; align-items:center'>"
            f"<div><div style='font-weight:700; font-size:1.05rem'>{r['event']}</div>"
            f"<div style='color:var(--blue); font-size:.85rem; margin-top:4px'>→ {r['action']}</div></div>"
            f"<div>{badge(r['date'], 'violet')}</div></div>",
            unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    styled_table(df)
    export_buttons(df, "amazon_events")

    if st.button("➕ Add events to Tasks"):
        for _, r in df.iterrows():
            db.add_task(f"Prepare for {r['event']} ({r['date']})", r["action"],
                        module="Event Planner", priority="low", related_id=r["event"])
        st.success("Events added to Tasks.")
