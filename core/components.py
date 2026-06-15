"""
core/components.py
==================
Reusable UI: KPI rows, styled HTML tables with conditional row highlighting,
page headers, and the shared CSV + Excel export buttons used on EVERY list page.

Excel export uses openpyxl via pandas; if openpyxl is missing we degrade to a
clear message rather than crashing.
"""

from __future__ import annotations
from io import BytesIO
import pandas as pd
import streamlit as st

from core.styles import kpi_card, badge, section_label


def kpi_row(cards: list[dict]) -> None:
    cols = st.columns(len(cards))
    for col, c in zip(cols, cards):
        with col:
            st.markdown(kpi_card(c["label"], c["value"], c.get("sub", ""),
                                 c.get("accent", "blue")), unsafe_allow_html=True)


def page_header(title: str, subtitle: str, icon: str = "") -> None:
    st.markdown(f"<h1 style='margin-bottom:2px'>{icon} {title}</h1>"
                f"<p style='color:var(--muted); margin-top:0; font-size:.95rem'>{subtitle}</p>",
                unsafe_allow_html=True)
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)


def styled_table(df: pd.DataFrame, highlight: dict | None = None,
                 badge_cols: dict | None = None) -> None:
    """Render a DataFrame as a premium HTML table.

    highlight  : {row_class: predicate(row)->bool}  (row-danger|row-warn|row-good)
    badge_cols : {col: {value: (text, kind)}}
    """
    highlight = highlight or {}
    badge_cols = badge_cols or {}
    head = "".join(f"<th>{c}</th>" for c in df.columns)
    body = []
    for _, row in df.iterrows():
        cls = ""
        for c, pred in highlight.items():
            try:
                if pred(row):
                    cls = c
                    break
            except Exception:
                continue
        cells = []
        for col in df.columns:
            val = row[col]
            if col in badge_cols and val in badge_cols[col]:
                text, kind = badge_cols[col][val]
                cells.append(f"<td>{badge(text, kind)}</td>")
            else:
                cells.append(f"<td>{val}</td>")
        body.append(f"<tr class='{cls}'>{''.join(cells)}</tr>")
    st.markdown(f"<table class='pretty-table'><thead><tr>{head}</tr></thead>"
                f"<tbody>{''.join(body)}</tbody></table>", unsafe_allow_html=True)


def export_buttons(df: pd.DataFrame, basename: str) -> None:
    """Render BOTH a CSV and an Excel download button side by side."""
    if df is None or df.empty:
        st.caption("Nothing to export yet.")
        return
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇ Export CSV", df.to_csv(index=False).encode("utf-8"),
                           file_name=f"{basename}.csv", mime="text/csv",
                           use_container_width=True, key=f"csv_{basename}")
    with c2:
        try:
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Data")
            st.download_button(
                "⬇ Export Excel", buf.getvalue(), file_name=f"{basename}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key=f"xlsx_{basename}")
        except Exception:
            st.caption("Install openpyxl for Excel export.")
