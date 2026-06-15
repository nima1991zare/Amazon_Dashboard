"""
core/api_client.py
==================
ABSTRACTION LAYER for every Amazon call (SP-API + Advertising API).

This is the single seam between the dashboard and Amazon. Methods that are wired
to the LIVE SP-API today (the listing-creation flow) call core/sp_api.py when
"Use MOCK Amazon" is OFF: get_product_types, get_listing_requirements,
search_catalog_items, validate_preview, push_listing(s).

Every OTHER method is not wired to a live endpoint yet, so it returns mock data
as a safe fallback (even in live mode) — this lets you go live for listing
creation without the rest of the dashboard crashing. Each such method has a
clearly-marked TODO showing the real endpoint to implement later.
"""

from __future__ import annotations
import pandas as pd

from core import mock_data
from core import db

USE_MOCK_DEFAULT = True


class ApiClient:
    """Facade over Amazon SP-API and Amazon Ads API."""

    def __init__(self, use_mock: bool | None = None):
        if use_mock is None:
            use_mock = db.get_setting("use_mock_amazon", "1") == "1"
        self.use_mock = use_mock

    def _credentials(self) -> dict:
        return {
            "refresh_token": db.get_setting("amazon_refresh_token", ""),
            "lwa_client_id": db.get_setting("amazon_lwa_client_id", ""),
            "lwa_client_secret": db.get_setting("amazon_lwa_client_secret", ""),
            "marketplace_id": db.get_setting("amazon_marketplace_id", "A2VIGQ35RCS4UG"),
            "ads_profile_id": db.get_setting("amazon_ads_profile_id", ""),
        }

    # =====================================================================
    # LIVE-WIRED: listing creation flow (uses core/sp_api.py when not mock)
    # =====================================================================
    def get_product_types(self, keywords: str = "") -> list:
        if self.use_mock:
            return mock_data.PRODUCT_TYPES
        from core import sp_api
        try:
            types = sp_api.search_product_types(keywords)
            if types:
                # Cache last-known-good list so a later network drop still works.
                db.set_setting("amazon_pt_cache", "\n".join(types))
                return types
        except Exception:
            pass  # network/SSL issue — fall back to cache, then mock
        cached = db.get_setting("amazon_pt_cache", "")
        if cached:
            return cached.splitlines()
        return mock_data.PRODUCT_TYPES

    def get_listing_requirements(self, product_type: str) -> list:
        if self.use_mock:
            return mock_data.listing_requirements(product_type)
        from core import sp_api
        return sp_api.get_requirements(product_type)

    def validate_listing(self, product_type: str, attributes: dict) -> dict:
        """Local required-completeness check (used by both mock and live UI)."""
        req = self.get_listing_requirements(product_type)
        missing = [f["name"] for f in req
                   if f.get("required") and not str(attributes.get(f["name"], "")).strip()]
        return {"ok": not missing, "missing": missing}

    def validate_preview(self, sku: str, product_type: str, attributes: dict) -> dict:
        """Listings Items VALIDATION_PREVIEW — validate against Amazon, no commit."""
        if self.use_mock:
            check = self.validate_listing(product_type, attributes)
            return {"ok": check["ok"], "status": "MOCK_VALID" if check["ok"] else "MOCK_INVALID",
                    "errors": [{"message": f"Missing: {x}"} for x in check["missing"]],
                    "issues": []}
        from core import sp_api
        return sp_api.validate_preview(sku, product_type, attributes)

    def search_catalog_items(self, identifier: str, id_type: str = "GTIN") -> list:
        if self.use_mock:
            return []
        from core import sp_api
        return sp_api.search_catalog_items(identifier, id_type)

    def push_listing(self, listing: dict) -> dict:
        """Create one listing. Validates required fields, then submits via Feeds."""
        attrs = listing.get("attributes", {})
        check = self.validate_listing(listing.get("product_type", "GENERIC"), attrs)
        if not check["ok"]:
            return {"status": "invalid", "missing": check["missing"]}
        if self.use_mock:
            return {"status": "mock_ok", "sku": listing.get("sku", ""),
                    "asin": "PENDING", "fields": len(attrs)}
        from core import sp_api
        sku = listing.get("sku", "")
        res = sp_api.submit_listings_feed([{
            "sku": sku, "product_type": listing.get("product_type", "GENERIC"),
            "attributes": attrs}])
        info = res.get("per_sku", {}).get(sku, {})
        status_map = {"accepted": "ok", "submitted": "submitted", "rejected": "error"}
        return {"status": status_map.get(info.get("status"), "error"),
                "feedId": res.get("feedId"), "processingStatus": res.get("processingStatus"),
                "issues": info.get("issues", []), "raw": res}

    def confirm_listing(self, sku: str) -> dict:
        """Directly confirm whether a listing was created (getListingsItem).
        Returns {exists, status, asin, issues}. Mock returns a stub."""
        if self.use_mock:
            return {"exists": True, "status": "MOCK_DISCOVERABLE",
                    "asin": "MOCK-ASIN", "issues": []}
        try:
            from core import sp_api
            return sp_api.get_listing_status(sku)
        except Exception as e:
            return {"exists": False, "status": "", "asin": "", "issues": [str(e)]}

    def push_listings_feed(self, items: list) -> dict:
        """Batch submit many listings in ONE JSON_LISTINGS_FEED."""
        if self.use_mock:
            per = {it["sku"]: {"status": "accepted", "issues": []} for it in items}
            return {"mode": "mock", "feedId": "MOCK-FEED", "processingStatus": "DONE",
                    "accepted": len(items), "rejected": 0, "per_sku": per}
        from core import sp_api
        return sp_api.submit_listings_feed(items)

    # =====================================================================
    # NOT-YET-LIVE: these return mock data as a safe fallback (even in live
    # mode) so the rest of the dashboard keeps working. TODOs mark the real
    # endpoints to wire later.
    # =====================================================================
    def get_my_listings(self) -> pd.DataFrame:
        # TODO(SP-API live): Reports GET_MERCHANT_LISTINGS_ALL_DATA → same columns.
        return mock_data.amazon_listings()

    def get_top_sellers_in_category(self, category: str) -> pd.DataFrame:
        # TODO(SP-API live): Catalog Items / Best Sellers ranking.
        return mock_data.top_sellers(category)

    def get_fees_estimate(self, asin: str, price: float) -> dict:
        # TODO(SP-API live): POST /products/fees/v0/items/{asin}/feesEstimate
        return mock_data.fees_estimate(asin, price)

    def get_lost_buybox(self) -> pd.DataFrame:
        # TODO(SP-API live): Product Pricing competitivePrice + offers.
        return mock_data.lost_buybox()

    def get_campaigns(self) -> pd.DataFrame:
        # TODO(Ads API live): POST /sp/campaigns/list + reporting v3.
        return mock_data.ad_campaigns()

    def get_keyword_targets(self, item: str) -> pd.DataFrame:
        # TODO(Ads API live): keyword/target reports + suggested bids.
        return mock_data.keyword_targets(item)

    def create_campaign(self, payload: dict) -> dict:
        # TODO(Ads API live): POST /sp/campaigns,/sp/adGroups,/sp/keywords
        return {"status": "mock_ok", "campaign": payload.get("name", "")}

    def get_deal_suggestions(self) -> pd.DataFrame:
        # TODO(live): Deals recommendations (limited public API).
        return mock_data.deal_suggestions()

    def get_market_comparison(self) -> pd.DataFrame:
        # TODO(SP-API live): Catalog + Pricing comparison.
        return mock_data.market_comparison()

    def get_fba_inventory(self) -> pd.DataFrame:
        if self.use_mock:
            return mock_data.fba_inventory()
        try:
            from core import sp_api
            raw = sp_api.get_fba_inventory_raw()
            rows = []
            for s in raw:
                rows.append({
                    "sku": s.get("sellerSku", ""), "title": s.get("productName", ""),
                    "fba_units": int(s.get("totalQuantity", 0) or 0),
                    "daily_velocity": 0.0, "days_in_fba": 0})
            return pd.DataFrame(rows) if rows else mock_data.fba_inventory()
        except Exception:
            return mock_data.fba_inventory()

    def get_events(self) -> pd.DataFrame:
        # TODO(live): curated calendar / Seller Central event scrape.
        return mock_data.amazon_events()

    def get_hazmat_compliance(self) -> pd.DataFrame:
        # TODO(live): FBA Compliance Dashboard (no public API yet) / export upload.
        return mock_data.hazmat_compliance()

    def upload_hazmat_file(self, content: bytes, filename: str) -> dict:
        # TODO(live): submit exemption sheet to compliance endpoint.
        return {"status": "mock_ok", "filename": filename, "bytes": len(content)}

    def set_fulfilment_channel(self, sku: str, channel: str) -> dict:
        # TODO(SP-API live): patchListingsItem fulfillment_availability FBA<->FBM.
        return {"status": "mock_ok", "sku": sku, "channel": channel}

    def get_inactive_listings(self) -> pd.DataFrame:
        # TODO(SP-API live): Listings/Reports filtered to status != ACTIVE.
        return mock_data.inactive_listings()

    def get_orders(self) -> pd.DataFrame:
        if self.use_mock:
            return mock_data.orders()
        try:
            from core import sp_api
            raw = sp_api.get_orders_raw(days=30, max_orders=60)
            rows = []
            for o in raw:
                total = o.get("OrderTotal") or {}
                rows.append({
                    "order_id": o.get("AmazonOrderId", ""),
                    "date": (o.get("PurchaseDate") or "")[:10],
                    "item": o.get("OrderType", "Order"),
                    "qty": int(o.get("NumberOfItemsShipped", 0) or 0),
                    "status": o.get("OrderStatus", ""),
                    "revenue": float(total.get("Amount", 0) or 0),
                    "cost": 0.0, "ad_spend": 0.0})
            return pd.DataFrame(rows) if rows else mock_data.orders()
        except Exception:
            return mock_data.orders()


def client() -> ApiClient:
    return ApiClient()
