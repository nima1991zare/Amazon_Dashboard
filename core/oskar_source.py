"""
core/oskar_source.py
====================
Product ENRICHMENT connector used by Auto Item Creation (Module 2).

Two modes:

  MODE A — PRICE LIST:
      You upload a price list (CSV/Excel) that already has price + details and a
      "media link" column. fetch_images_from_media_link() pulls the product
      image URLs from that link. Price/details come straight from the file.

  MODE B — URL:
      You paste an item URL from another site. scrape_product_from_url() extracts
      title, price, description, specs and images using GENERIC patterns
      (Open Graph tags, JSON-LD, then common CSS selectors). Site-specific
      selectors can be layered on later.

USE_MOCK is on by default so the demo works with no network. When you wire the
real connect.oskarme.com API, fill the TODO stubs and flip USE_MOCK.

Network calls use requests + BeautifulSoup and are wrapped defensively: any
failure returns an empty/partial result with a reason, never raises into the UI.
"""

from __future__ import annotations
import re

from core import mock_data
from core import db

USE_MOCK_DEFAULT = True


def _use_mock() -> bool:
    return db.get_setting("use_mock_oskar", "1") == "1"


# ---------------------------------------------------------------------------
# MODE A — images from a media link in the price list
# ---------------------------------------------------------------------------
_IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _collect_image_urls(obj, out: list) -> None:
    """Recursively pull image URLs out of an arbitrary JSON structure."""
    if isinstance(obj, str):
        low = obj.lower().split("?")[0]
        if obj.startswith("http") and (low.endswith(_IMG_EXT) or "/media/" in obj.lower()
                                        or "image" in obj.lower()):
            out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_image_urls(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_image_urls(v, out)


def fetch_images_from_media_link(media_link: str, sku: str = "") -> dict:
    """Fetch product images from connect.oskarme.com.

    Calls GET {base}/api/v1/product/combined-media?item=<sku> with a Bearer token
    (oskar_token from Settings). The SKU is taken from `sku` or extracted from a
    /doc/<SKU> media link. Returns {'images':[url,...], 'ok':bool, 'reason':str}.
    """
    if _use_mock():
        return mock_data.oskar_media_images(sku, media_link)

    # Resolve the item identifier (SKU) — from the arg or the /doc/<SKU> link.
    item = str(sku).strip()
    if not item and media_link:
        m = re.search(r"/doc/([^/?#]+)", str(media_link))
        if m:
            item = m.group(1)
    if not item:
        return {"images": [], "ok": False, "reason": "no SKU/item to look up"}

    base = (db.get_setting("oskar_base_url", "https://connect.oskarme.com") or
            "https://connect.oskarme.com").rstrip("/")
    token = db.get_setting("oskar_token", "")
    try:
        import requests
        headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        if token:
            headers["Authorization"] = token   # raw token, NOT "Bearer ..."
        r = requests.get(f"{base}/api/v1/product/combined-media",
                         params={"item": item}, headers=headers, timeout=25)
        if r.status_code == 401:
            return {"images": [], "ok": False,
                    "reason": "oskar unauthorized — add/refresh your oskar token in Settings"}
        r.raise_for_status()
        data = r.json()
        media = (data.get("data") or {}).get("media") or {}
        # Product images live at data.media.primaryImage + data.media.images.
        imgs: list = []
        if media.get("primaryImage"):
            imgs.append(media["primaryImage"])
        for u in (media.get("images") or []):
            if u:
                imgs.append(u)
        if not imgs:                       # fallback if the shape ever differs
            _collect_image_urls(data, imgs)
        imgs = [u for u in dict.fromkeys(imgs) if isinstance(u, str) and u.startswith("http")][:12]
        return {"images": imgs, "ok": bool(imgs),
                "reason": "" if imgs else "no images in oskar response"}
    except Exception as e:
        return {"images": [], "ok": False, "reason": f"oskar fetch error: {e}"}


# ---------------------------------------------------------------------------
# MODE B — scrape a product page generically
# ---------------------------------------------------------------------------
_PRICE_RE = re.compile(r"(\d[\d,]*\.?\d*)")


def scrape_product_from_url(url: str) -> dict:
    """Return a normalized draft listing dict:
       {title, price, description, specs(dict), images[list], ok, reason}.
    """
    if not url or not str(url).strip():
        return {"ok": False, "reason": "no url", "title": "", "price": None,
                "description": "", "specs": {}, "images": []}

    if _use_mock():
        return mock_data.oskar_scrape(url)

    # TODO(connect.oskarme.com): if the URL belongs to a supported source, call
    # the oskarme enrichment API instead of generic scraping for better fidelity.
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0 (DashboardBot)"})
        soup = BeautifulSoup(resp.text, "html.parser")

        def og(prop):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            return tag.get("content") if tag and tag.get("content") else ""

        # 1) Open Graph first.
        title = og("og:title") or (soup.title.string.strip() if soup.title else "")
        description = og("og:description")
        images: list[str] = []
        for tag in soup.find_all("meta", property="og:image"):
            if tag.get("content"):
                images.append(tag["content"])

        # 2) JSON-LD Product (most reliable for price/brand/images/specs).
        price = None
        brand = ""
        specs: dict = {}
        import json
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
            except Exception:
                continue
            blocks = data if isinstance(data, list) else [data]
            # also unwrap @graph
            flat = []
            for b in blocks:
                if isinstance(b, dict) and "@graph" in b:
                    flat.extend(b["@graph"])
                else:
                    flat.append(b)
            for b in flat:
                if not isinstance(b, dict):
                    continue
                t = b.get("@type", "")
                if (t == "Product") or (isinstance(t, list) and "Product" in t):
                    title = title or b.get("name", "")
                    description = description or b.get("description", "")
                    br = b.get("brand")
                    brand = brand or (br.get("name") if isinstance(br, dict) else (br or ""))
                    img = b.get("image")
                    if isinstance(img, str):
                        images.append(img)
                    elif isinstance(img, list):
                        images.extend([i for i in img if isinstance(i, str)])
                    offers = b.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    if isinstance(offers, dict):
                        price = price or offers.get("price") or offers.get("lowPrice")

        # 3) Heuristic price fallback from common selectors.
        if price is None:
            node = soup.select_one("[class*=price], [id*=price], [itemprop=price]")
            if node:
                m = _PRICE_RE.search(node.get("content") or node.get_text())
                if m:
                    price = m.group(1).replace(",", "")

        # de-dup images, keep order, http only
        seen, imgs = set(), []
        for u in images:
            if u and u.startswith("http") and u not in seen:
                seen.add(u)
                imgs.append(u)

        try:
            price = float(price) if price not in (None, "") else None
        except (TypeError, ValueError):
            price = None

        return {"ok": bool(title), "reason": "" if title else "could not parse title",
                "title": title, "price": price, "brand": brand,
                "description": description, "specs": specs, "images": imgs[:8]}
    except Exception as e:
        return {"ok": False, "reason": f"scrape error: {e}", "title": "", "price": None,
                "description": "", "specs": {}, "images": []}
