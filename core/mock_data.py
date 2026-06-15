"""
core/mock_data.py
=================
All mock datasets, cached, so the entire dashboard is populated and interactive
on first launch with zero network/API access. Every function here mirrors the
shape of the real data the api_client / connectors will return later, so swapping
USE_MOCK off requires no UI changes.
"""

from __future__ import annotations
import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# LISTINGS / CATALOG
# ---------------------------------------------------------------------------
@st.cache_data
def amazon_listings() -> pd.DataFrame:
    """Active Amazon.ae listings (your live catalog)."""
    return pd.DataFrame([
        ["BTS-FIT3-BLK", "B09JL41N9C", "Beats Fit Pro - Black",          "Beats",   "Audio",       4,  2.4, 649],
        ["ANK-737-PB",   "B09VPHVT2Z", "Anker 737 Power Bank 24000mAh",  "Anker",   "Charging",    28, 1.1, 499],
        ["XMI-CW300",    "B0CX1Q9R2L", "Xiaomi Smart Camera CW300",      "Xiaomi",  "Smart Home",  0,  3.0, 179],
        ["JBL-PB710",    "B0BR5T9K8M", "JBL PartyBox 710",               "JBL",     "Audio",       6,  0.7, 2299],
        ["BOS-QC45-WHT", "B098FKXT8L", "Bose QuietComfort 45 - White",   "Bose",    "Audio",       31, 1.6, 999],
        ["APL-APP2",     "B0BDHWDR12", "Apple AirPods Pro (2nd Gen)",    "Apple",   "Audio",       2,  5.2, 879],
        ["GRN-LION-PD",  "B0C3K2L9PP", "Green Lion 65W GaN Charger",     "Green Lion","Charging",  44, 0.9, 129],
        ["SAM-S24U-256", "B0CMDRCZBJ", "Samsung Galaxy S24 Ultra 256GB", "Samsung", "Phones",      9,  1.4, 4399],
    ], columns=["sku", "asin", "title", "brand", "category", "fba_stock",
                "daily_velocity", "price"])


def catalog_seed() -> list[dict]:
    """Baseline catalog rows for db.seed_catalog_if_empty()."""
    df = amazon_listings()
    return df[["sku", "asin", "title", "brand", "category"]].to_dict("records")


# ---------------------------------------------------------------------------
# INVENTORY-WEBSITE FETCH  (inventory_source mock)
# ---------------------------------------------------------------------------
@st.cache_data
def inventory_website_items() -> pd.DataFrame:
    """What the inventory website would return — includes items NOT yet listed."""
    return pd.DataFrame([
        ["BTS-FIT3-BLK", "Beats Fit Pro - Black",          "Beats",     "Audio",      120, 360],
        ["ANK-737-PB",   "Anker 737 Power Bank 24000mAh",  "Anker",     "Charging",   60,  300],
        ["XMI-CW300",    "Xiaomi Smart Camera CW300",      "Xiaomi",    "Smart Home", 200, 110],
        ["APL-APP2",     "Apple AirPods Pro (2nd Gen)",    "Apple",     "Audio",      340, 560],
        ["DYS-V15-DETC", "Dyson V15 Detect Absolute",      "Dyson",     "Home",       45,  2599],  # NEW
        ["MAR-EMB3-BLK", "Marshall Emberton III - Black",  "Marshall",  "Audio",      88,  549],   # NEW
        ["LEP-MAGSAFE",  "Lepresso 15W MagSafe Stand",     "Lepresso",  "Charging",   150, 95],    # NEW
        ["SAM-S24U-256", "Samsung Galaxy S24 Ultra 256GB", "Samsung",   "Phones",     30,  4399],
    ], columns=["sku", "title", "brand", "category", "warehouse_qty", "cost"])


# ---------------------------------------------------------------------------
# PRICE LIST  (Auto Item Creation, Mode A)
# ---------------------------------------------------------------------------
@st.cache_data
def sample_price_list() -> pd.DataFrame:
    """A price list with a media-link column, as a seller would upload."""
    return pd.DataFrame([
        ["DYS-V15-DETC", "Dyson V15 Detect Absolute",  "Dyson",    2599, "https://media.oskarme.com/dyson_v15"],
        ["MAR-EMB3-BLK", "Marshall Emberton III Black", "Marshall", 549,  "https://media.oskarme.com/marshall_emb3"],
        ["LEP-MAGSAFE",  "Lepresso 15W MagSafe Stand",  "Lepresso", 95,   ""],  # missing media → amber flag
    ], columns=["sku", "title", "brand", "price", "media_link"])


def oskar_media_images(sku: str, media_link: str) -> dict:
    """Mock image fetch keyed off the media link."""
    catalog = {
        "DYS-V15-DETC": ["https://media.oskarme.com/dyson_v15/main.jpg",
                         "https://media.oskarme.com/dyson_v15/side.jpg"],
        "MAR-EMB3-BLK": ["https://media.oskarme.com/marshall_emb3/main.jpg"],
    }
    imgs = catalog.get(sku, [])
    return {"images": imgs, "ok": bool(imgs),
            "reason": "" if imgs else "media link empty or unmapped (mock)"}


def oskar_scrape(url: str) -> dict:
    """Mock generic URL scrape (Auto Item Creation, Mode B)."""
    return {
        "ok": True, "reason": "",
        "title": "JBL Flip 6 Portable Bluetooth Speaker - Blue",
        "price": 399.0,
        "description": "Bold sound, IP67 waterproof + dustproof, 12 hours of playtime.",
        "specs": {"Battery": "12h", "Waterproof": "IP67", "Weight": "550g"},
        "images": ["https://img.example.com/jbl_flip6_main.jpg",
                   "https://img.example.com/jbl_flip6_alt.jpg"],
        "source_url": url,
    }


# ---------------------------------------------------------------------------
# LISTING OPTIMIZATION
# ---------------------------------------------------------------------------
def top_sellers(category: str) -> pd.DataFrame:
    """Best-sellers in a category whose keywords we'll mine."""
    base = {
        "Audio": [
            ["Sony WF-1000XM5", "noise cancelling earbuds wireless bluetooth sweatproof", 999],
            ["Apple AirPods Pro 2", "anc earbuds apple h2 spatial audio", 879],
            ["JBL Tune Flex", "wireless earbuds bass jbl waterproof", 299],
        ],
        "Charging": [
            ["Anker Prime 200W", "gan charger fast usb-c power bank laptop", 599],
            ["Belkin BoostCharge", "magsafe wireless charger 15w stand", 199],
        ],
        "Smart Home": [
            ["TP-Link Tapo C200", "wifi security camera 360 night vision indoor", 99],
            ["Ring Indoor Cam", "smart camera two way audio motion", 199],
        ],
    }
    rows = base.get(category, [["Generic Best Seller", "popular trending value", 199]])
    return pd.DataFrame(rows, columns=["title", "keywords", "price"])


def optimized_listing(title_seed: str, category: str, keywords: str) -> dict:
    """A deterministic 'optimized' listing (rule-based fallback for the optimizer)."""
    kw = keywords.split()[:6]
    return {
        "title": f"{title_seed} – {category} | "
                 f"{' '.join(w.capitalize() for w in kw[:4])} (UAE Warranty)"[:200],
        "bullets": [
            f"PREMIUM {category.upper()} – engineered for everyday performance and reliability.",
            f"KEY FEATURES – {', '.join(kw[:4])} for a standout experience.",
            "FAST UAE DELIVERY – ships from local stock with hassle-free returns.",
            "BUILT TO LAST – quality materials and trusted brand support.",
            "GREAT VALUE – competitively priced against category best-sellers.",
        ],
        "keywords": ", ".join(dict.fromkeys(kw + [category.lower(), "uae", "dubai"])),
        "description": f"The {title_seed} brings together {', '.join(kw[:3])} in a "
                       f"reliable {category.lower()} package. Designed for UAE customers "
                       f"who want quality and value with local support.",
    }


# ---------------------------------------------------------------------------
# FEES / PRICING
# ---------------------------------------------------------------------------
def fees_estimate(asin: str, price: float) -> dict:
    """Mock SP-API fee estimate."""
    referral = round(price * 0.15, 2)
    fba = 14.0
    return {"referral_fee": referral, "fba_fee": fba, "closing_fee": 0.0,
            "total_fees": round(referral + fba, 2)}


def lost_buybox() -> pd.DataFrame:
    return pd.DataFrame([
        ["BTS-FIT3-BLK", "Beats Fit Pro - Black",       649, 619, "ColdStorageAE"],
        ["APL-APP2",     "Apple AirPods Pro (2nd Gen)", 879, 859, "GadgetHub"],
        ["XMI-CW300",    "Xiaomi Smart Camera CW300",   179, 165, "SmartLifeUAE"],
    ], columns=["sku", "title", "your_price", "buybox_price", "buybox_winner"])


def market_comparison() -> pd.DataFrame:
    return pd.DataFrame([
        ["Beats Fit Pro - Black",     649, 612, 38500, "Rising",   "Trending"],
        ["Anker 737 Power Bank",      499, 470, 12200, "Flat",     "Stable"],
        ["Xiaomi CW300 Camera",       179, 158, 51000, "Rising",   "Trending"],
        ["Bose QC45 - White",         999, 905, 8400,  "Falling",  "Declining"],
        ["Green Lion 65W Charger",    129, 110, 3100,  "Rising",   "Hidden Gem"],
    ], columns=["item", "your_price", "market_min", "monthly_demand", "trend", "signal"])


# ---------------------------------------------------------------------------
# COMPETITOR PRICES  (Noon / other UAE — market tracker mock)
# ---------------------------------------------------------------------------
def competitor_prices(item_name: str) -> pd.DataFrame:
    return pd.DataFrame([
        ["Amazon.ae", 649],
        ["Noon.com", 599],
        ["SharafDG", 679],
        ["Jumbo", 665],
    ], columns=["source", "price"])


# ---------------------------------------------------------------------------
# ADVERTISING
# ---------------------------------------------------------------------------
@st.cache_data
def ad_campaigns() -> pd.DataFrame:
    return pd.DataFrame([
        ["SP - Beats Fit Pro Exact", 312, 240, 48200, 612, 18.4, 1695],
        ["SP - Anker Charging Auto",  96, 110, 22100, 305, 12.1,  793],
        ["SP - Xiaomi Camera Broad", 188, 150, 39800, 540, 29.7,  633],
        ["SP - Bose Premium Exact",  142, 180, 15600, 198,  9.8, 1449],
        ["SP - AirPods Defensive",   401, 300, 61200, 884, 22.5, 1782],
    ], columns=["campaign", "spend_today", "avg_daily", "impressions",
                "clicks", "acos", "sales"])


def keyword_targets(item: str) -> pd.DataFrame:
    return pd.DataFrame([
        ["wireless earbuds",        2.10, 1.80, 22.0, "Raise"],
        ["beats fit pro",           1.40, 1.60, 11.0, "Hold"],
        ["noise cancelling earbuds",2.80, 2.10, 31.0, "Lower"],
        ["workout earphones",       1.10, 1.30,  9.0, "Raise"],
    ], columns=["keyword", "current_bid", "suggested_bid", "acos", "action"])


# ---------------------------------------------------------------------------
# DEALS
# ---------------------------------------------------------------------------
def deal_suggestions() -> pd.DataFrame:
    return pd.DataFrame([
        ["Bose QC45 - White",        999, 849, "Lightning Deal", 34],
        ["Green Lion 65W Charger",   129, 109, "7-Day Deal",     38],
        ["Marshall Emberton III",    549, 469, "Best Deal",      41],
    ], columns=["item", "current_price", "suggested_deal_price", "deal_type", "margin_pct"])


# ---------------------------------------------------------------------------
# ASSET MANAGEMENT  (A+ content + video status)
# ---------------------------------------------------------------------------
def asset_status() -> pd.DataFrame:
    return pd.DataFrame([
        ["Beats Fit Pro - Black",       "Ready",     "Uploaded",     "https://video.site/beats"],
        ["Anker 737 Power Bank",        "Ready",     "Uploaded",     "https://video.site/anker737"],
        ["Xiaomi CW300 Camera",         "Draft",     "Not Uploaded", ""],
        ["Dyson V15 Detect",            "Suggested", "Not Uploaded", ""],
        ["Marshall Emberton III",       "Suggested", "Uploaded",     "https://video.site/marshall"],
    ], columns=["item", "aplus_status", "video_status", "video_link"])


# ---------------------------------------------------------------------------
# FBA / WAREHOUSE
# ---------------------------------------------------------------------------
def fba_inventory() -> pd.DataFrame:
    return pd.DataFrame([
        ["BTS-FIT3-BLK", "Beats Fit Pro - Black",       4,  2.4, 30],
        ["APL-APP2",     "Apple AirPods Pro (2nd Gen)", 2,  5.2, 30],
        ["BOS-QC45-WHT", "Bose QuietComfort 45 - White",31, 1.6, 30],
        ["JBL-PB710",    "JBL PartyBox 710",            6,  0.7, 90],   # slow → stuck
        ["GRN-LION-PD",  "Green Lion 65W GaN Charger",  44, 0.2, 180],  # very slow → stuck
    ], columns=["sku", "title", "fba_units", "daily_velocity", "days_in_fba"])


# ---------------------------------------------------------------------------
# EVENTS
# ---------------------------------------------------------------------------
def amazon_events() -> pd.DataFrame:
    return pd.DataFrame([
        ["2026-06-16", "Eid Al Adha",            "Adjust stock & raise ad budgets 30%"],
        ["2026-07-01", "Amazon.ae Summer Sale",  "Submit deal nominations by Jun 20"],
        ["2026-08-25", "Back to School",         "Bundle chargers + power banks"],
        ["2026-11-28", "White Friday",           "Biggest event — lock stock & deals early"],
    ], columns=["date", "event", "action"])


# ---------------------------------------------------------------------------
# ORDERS / PROFIT
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# AMAZON LISTING REQUIRED FIELDS  (mock of Product Type Definitions API)
# ---------------------------------------------------------------------------
# Each field: name, label, required, type, and optional source/options/default.
# `source` maps to a draft/optimized field so we can pre-fill automatically.
PRODUCT_TYPES = ["HEADPHONES", "SPEAKERS", "POWER_BANK", "CHARGER",
                 "PHONE_CASE", "CAMERA", "SMARTWATCH", "GENERIC"]

_BASE_REQUIRED = [
    {"name": "item_name", "label": "Title", "required": True, "type": "text",
     "max": 200, "source": "title"},
    {"name": "brand", "label": "Brand", "required": True, "type": "text", "source": "brand"},
    {"name": "manufacturer", "label": "Manufacturer", "required": True, "type": "text",
     "source": "brand"},
    {"name": "external_product_id", "label": "Barcode (UPC/EAN/GTIN)", "required": True,
     "type": "text", "help": "Amazon requires a Product ID unless GTIN-exempt."},
    {"name": "external_product_id_type", "label": "Barcode type", "required": True,
     "type": "select", "options": ["UPC", "EAN", "GTIN", "GCID"], "default": "EAN"},
    {"name": "bullet_point", "label": "Bullet Points (key features)", "required": True,
     "type": "textarea", "source": "bullets"},
    {"name": "product_description", "label": "Description", "required": True,
     "type": "textarea", "source": "description"},
    {"name": "standard_price", "label": "Price (AED)", "required": True, "type": "number",
     "source": "price"},
    {"name": "quantity", "label": "Quantity", "required": True, "type": "number", "default": 1},
    {"name": "condition_type", "label": "Condition", "required": True, "type": "select",
     "options": ["new_new", "used_like_new", "used_good", "refurbished_refurbished"],
     "default": "new_new"},
    {"name": "main_image_url", "label": "Main image URL", "required": True, "type": "text",
     "source": "image"},
    {"name": "country_of_origin", "label": "Country of origin", "required": True,
     "type": "text", "default": "China"},
    {"name": "fulfillment_channel", "label": "Fulfilment channel", "required": True,
     "type": "select", "options": ["FBM", "FBA"], "default": "FBM"},
]

_TYPE_EXTRA = {
    "HEADPHONES": [
        {"name": "color", "label": "Color", "required": True, "type": "text"},
        {"name": "model_number", "label": "Model number", "required": True, "type": "text"},
        {"name": "connectivity_technology", "label": "Connectivity", "required": True,
         "type": "select", "options": ["Bluetooth", "Wired", "Wireless"], "default": "Bluetooth"},
        {"name": "batteries_required", "label": "Batteries required?", "required": True,
         "type": "select", "options": ["Yes", "No"], "default": "Yes"},
    ],
    "SPEAKERS": [
        {"name": "color", "label": "Color", "required": True, "type": "text"},
        {"name": "model_number", "label": "Model number", "required": True, "type": "text"},
        {"name": "connectivity_technology", "label": "Connectivity", "required": True,
         "type": "select", "options": ["Bluetooth", "Wired", "Wi-Fi"], "default": "Bluetooth"},
    ],
    "POWER_BANK": [
        {"name": "color", "label": "Color", "required": True, "type": "text"},
        {"name": "model_number", "label": "Model number", "required": True, "type": "text"},
        {"name": "battery_cell_composition", "label": "Battery cell composition",
         "required": True, "type": "select",
         "options": ["Lithium Ion", "Lithium Polymer"], "default": "Lithium Ion"},
        {"name": "number_of_lithium_ion_cells", "label": "No. of Li-ion cells",
         "required": True, "type": "number", "default": 1},
        {"name": "watt_hours", "label": "Watt-hours (Wh)", "required": True, "type": "number"},
    ],
    "CHARGER": [
        {"name": "color", "label": "Color", "required": True, "type": "text"},
        {"name": "model_number", "label": "Model number", "required": True, "type": "text"},
        {"name": "wattage", "label": "Wattage (W)", "required": True, "type": "number"},
        {"name": "plug_format", "label": "Plug format", "required": True, "type": "text",
         "default": "UK 3-pin"},
    ],
    "PHONE_CASE": [
        {"name": "color", "label": "Color", "required": True, "type": "text"},
        {"name": "material", "label": "Material", "required": True, "type": "text"},
        {"name": "compatible_devices", "label": "Compatible devices", "required": True,
         "type": "text"},
    ],
    "CAMERA": [
        {"name": "color", "label": "Color", "required": True, "type": "text"},
        {"name": "model_number", "label": "Model number", "required": True, "type": "text"},
        {"name": "effective_still_resolution", "label": "Megapixels", "required": True,
         "type": "text"},
    ],
    "SMARTWATCH": [
        {"name": "color", "label": "Color", "required": True, "type": "text"},
        {"name": "model_number", "label": "Model number", "required": True, "type": "text"},
        {"name": "screen_size", "label": "Screen size (in)", "required": True, "type": "text"},
    ],
    "GENERIC": [],
}


def listing_requirements(product_type: str) -> list[dict]:
    """Mock the required-attributes schema Amazon returns for a product type."""
    fields = [dict(f) for f in _BASE_REQUIRED]
    fields += [dict(f) for f in _TYPE_EXTRA.get(product_type, [])]
    return fields


# ---------------------------------------------------------------------------
# HAZMAT / DANGEROUS GOODS COMPLIANCE  (FBA Compliance Dashboard)
# ---------------------------------------------------------------------------
# Exact headers of Amazon's Battery Exemption (Dangerous Goods) template.
HAZMAT_TEMPLATE_HEADERS = [
    "ASIN", "Product title", "What's in the box?",
    "Are batteries sold with the product or is the product a battery?",
    "Chemical composition / cell type of the battery", "Battery packaging",
    "No. of cells", "Watt-hours", "Spillability", "Details validation status",
]
# Allowed dropdown values (from the template's Formula sheets).
HAZMAT_ALLOWED = {
    "sold": ["Yes", "No"],
    "chemical": ["_18650_", "Alkaline", "Carbon Zinc", "CR2032", "Lead Acid",
                 "Lead Calcium", "Lithium cobalt oxide", "Lithium Ion",
                 "Lithium iron phosphate", "Lithium Metal",
                 "Lithium nickel manganese cobalt oxide", "Lithium Polymer",
                 "Lithium thionyl chloride", "Lithium titanate", "LR44",
                 "Nickel Cadmium", "Nickel Metal Hydride", "Silver Oxide",
                 "Zinc", "Zinc air", "Zinc Carbon"],
    "packaging": ["In Equipment", "With Equipment", "Standalone"],
    "cells": ["Single_cell", "Multiple_cells"],
    "watt_hours": ["WH <= 100", "101 - 300 WH", "WH > 300"],
    "spillability": ["Spillable", "Non-Spillable"],
}

# The three statuses Amazon's compliance dashboard reports.
HAZMAT_UNABLE = "Unable to classify"
HAZMAT_FULFILLABLE = "Dangerous Good FBA Fulfillable"
HAZMAT_UNFULFILLABLE = "Dangerous Good Unfulfillable"


def hazmat_compliance() -> pd.DataFrame:
    """Mock of the FBA compliance dashboard export."""
    return pd.DataFrame([
        ["B09VPHVT2Z", "ANK-737-PB",   "Anker 737 Power Bank 24000mAh",  HAZMAT_UNABLE,        "FBM"],
        ["B0C3K2L9PP", "GRN-LION-PD",  "Green Lion 65W GaN Charger",     HAZMAT_UNABLE,        "FBM"],
        ["B0BDHWDR12", "APL-APP2",     "Apple AirPods Pro (2nd Gen)",    HAZMAT_FULFILLABLE,   "FBM"],
        ["B0CMDRCZBJ", "SAM-S24U-256", "Samsung Galaxy S24 Ultra 256GB", HAZMAT_FULFILLABLE,   "FBA"],
        ["B0CX1Q9R2L", "XMI-CW300",    "Xiaomi Smart Camera CW300",      HAZMAT_UNFULFILLABLE, "FBA"],
        ["B0BR5T9K8M", "JBL-PB710",    "JBL PartyBox 710",               HAZMAT_UNFULFILLABLE, "FBA"],
    ], columns=["asin", "sku", "title", "hazmat_status", "fulfilment_channel"])


# ---------------------------------------------------------------------------
# INACTIVE LISTINGS
# ---------------------------------------------------------------------------
def inactive_listings() -> pd.DataFrame:
    return pd.DataFrame([
        ["B0CX1Q9R2L", "XMI-CW300",    "Xiaomi Smart Camera CW300",     "Inactive", "Out of stock",          "2026-05-22"],
        ["B098FKXT8L", "BOS-QC45-WHT", "Bose QuietComfort 45 - White",  "Inactive", "Suppressed — main image","2026-05-30"],
        ["B0C3K2L9PP", "GRN-LION-PD",  "Green Lion 65W GaN Charger",    "Inactive", "Pricing error (too high)","2026-06-01"],
        ["B0BR5T9K8M", "JBL-PB710",    "JBL PartyBox 710",              "Inactive", "Search suppressed",      "2026-05-18"],
        ["B09JL41N9C", "BTS-FIT3-BLK", "Beats Fit Pro - Black",         "Inactive", "Closed by seller",       "2026-04-11"],
    ], columns=["asin", "sku", "title", "status", "reason", "last_active"])


@st.cache_data
def orders() -> pd.DataFrame:
    import itertools
    rows = []
    data = [
        ("Beats Fit Pro - Black", 649, 380, 35, "2026-06-01"),
        ("Apple AirPods Pro 2",   879, 720, 40, "2026-06-02"),
        ("Anker 737 Power Bank",  499, 300, 22, "2026-06-02"),
        ("Xiaomi CW300 Camera",   179, 120, 18, "2026-06-03"),
        ("Bose QC45 - White",     999, 650, 30, "2026-06-04"),
        ("Green Lion 65W Charger",129, 70,  8,  "2026-06-05"),
    ]
    oid = itertools.count(40021)
    for item, rev, cost, ad, date in data:
        for q in [1, 2]:
            rows.append([f"#{next(oid)}", date, item, q, "Shipped",
                         rev * q, cost * q, ad])
    return pd.DataFrame(rows, columns=["order_id", "date", "item", "qty",
                                       "status", "revenue", "cost", "ad_spend"])
