"""
core/util.py
============
Shared helpers for messy real-world files: flexible column detection (so uploads
work regardless of exact header names) and simple fuzzy item matching across the
Amazon and warehouse files.

This is what lets the seller upload their existing CSVs/Excels (SKU vs sku vs
"Seller SKU", Price vs price vs "Unit Price", etc.) without renaming columns.
"""

from __future__ import annotations
import re
import difflib
import pandas as pd

# Candidate header keywords for each logical field, in priority order.
_FIELD_ALIASES = {
    "sku":        ["sku", "seller sku", "sellersku", "item code", "code"],
    "asin":       ["asin", "amazon asin"],
    "barcode":    ["barcode", "ean", "upc", "gtin"],
    "title":      ["title", "name", "product", "description", "item"],
    "brand":      ["brand", "manufacturer", "vendor"],
    "category":   ["category", "type", "department"],
    "price":      ["price", "cost", "unit price", "selling price", "mrp"],
    "qty":        ["qty", "quantity", "stock", "available", "on hand", "units", "warehouse_qty", "fba_stock"],
    "media_link": ["media", "media link", "media_link", "image", "images", "image link", "photo", "link"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def find_column(df: pd.DataFrame, field: str) -> str | None:
    """Return the best-matching column name in df for a logical field, or None."""
    aliases = _FIELD_ALIASES.get(field, [field])
    norm_cols = {_norm(c): c for c in df.columns}
    # 1) exact normalized alias hit
    for a in aliases:
        if _norm(a) in norm_cols:
            return norm_cols[_norm(a)]
    # 2) substring containment
    for a in aliases:
        for nc, original in norm_cols.items():
            if _norm(a) in nc:
                return original
    return None


def get_field(df: pd.DataFrame, field: str, default=None) -> pd.Series:
    """Return the Series for a logical field, or a default-filled Series."""
    col = find_column(df, field)
    if col is not None:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)


def fuzzy_match_key(value: str, choices: list[str], cutoff: float = 0.82) -> str | None:
    """Return the closest choice to `value` above cutoff, else None."""
    if not value:
        return None
    matches = difflib.get_close_matches(str(value), [str(c) for c in choices],
                                        n=1, cutoff=cutoff)
    return matches[0] if matches else None
