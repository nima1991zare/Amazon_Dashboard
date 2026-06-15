"""
core/inventory_source.py
========================
Connector to YOUR inventory website. Returns the current product list as a
DataFrame. USE_MOCK is on by default; flip it (Settings → "Use mock inventory")
and fill the TODO once your endpoint + auth are configured.

Base URL + auth token are read from Settings (DB), so nothing is hard-coded.
All network failures degrade gracefully to an empty frame + reason.
"""

from __future__ import annotations
import pandas as pd

from core import mock_data
from core import db


def _use_mock() -> bool:
    return db.get_setting("use_mock_inventory", "1") == "1"


def fetch_inventory() -> tuple[pd.DataFrame, str]:
    """Return (items_df, status_message)."""
    if _use_mock():
        return mock_data.inventory_website_items(), "mock data (Settings → toggle to go live)"

    base_url = db.get_setting("inventory_base_url", "")
    token = db.get_setting("inventory_auth_token", "")
    if not base_url:
        return pd.DataFrame(), "no inventory_base_url set in Settings"

    # TODO(inventory website): replace with your real endpoint + response mapping.
    # Expected to return columns: sku, title, brand, category, warehouse_qty, cost
    try:
        import requests
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(f"{base_url.rstrip('/')}/api/products",
                            headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        return df, f"live: {len(df)} items"
    except Exception as e:
        return pd.DataFrame(), f"fetch error: {e}"


def fetch_video_links() -> pd.DataFrame:
    """Published video links per item (Asset Management). Mock for now."""
    if _use_mock():
        return mock_data.asset_status()[["item", "video_status", "video_link"]]
    # TODO(inventory website / sheet): pull the published-video sheet here.
    return pd.DataFrame(columns=["item", "video_status", "video_link"])
