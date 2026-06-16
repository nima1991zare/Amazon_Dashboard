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


_CONNECT_SESSION = None


def _connect_session():
    """Shared, connection-pooled session so bulk lookups reuse TCP/TLS connections
    (one handshake instead of one-per-SKU) — the main reason sequential was slow."""
    global _CONNECT_SESSION
    if _CONNECT_SESSION is None:
        import requests
        from requests.adapters import HTTPAdapter
        s = requests.Session()
        ad = HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=1)
        s.mount("https://", ad)
        s.mount("http://", ad)
        _CONNECT_SESSION = s
    return _CONNECT_SESSION


def _parse_connect(data_json, sku) -> dict:
    data = (data_json or {}).get("data") or {}
    media = data.get("media") or {}
    imgs = []
    if media.get("primaryImage"):
        imgs.append(media["primaryImage"])
    imgs += [u for u in (media.get("images") or []) if u]
    imgs = [u for u in dict.fromkeys(imgs) if isinstance(u, str) and u.startswith("http")]
    return {"ok": True, "sku": sku, "data": data, "images": imgs, "reason": ""}


def _fetch_one(sess, base: str, token: str, sku: str, timeout: int = 12) -> dict:
    """One connect GET using a shared session. No DB access (safe to call in threads)."""
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    if token:
        headers["Authorization"] = token   # raw token, NOT "Bearer ..."
    try:
        r = sess.get(f"{base}/api/v1/product/combined-media",
                     params={"item": sku}, headers=headers, timeout=timeout)
        if r.status_code == 401:
            return {"ok": False, "sku": sku, "data": {}, "images": [],
                    "reason": "unauthorized — add/refresh your oskar token in Settings"}
        r.raise_for_status()
        return _parse_connect(r.json(), sku)
    except Exception as e:
        return {"ok": False, "sku": sku, "data": {}, "images": [], "reason": f"connect error: {e}"}


def fetch_product_info(sku: str) -> dict:
    """Fetch the FULL product record for ONE SKU from connect.oskarme.com.
    Returns {'ok':bool, 'sku':sku, 'data':<raw 'data' object>, 'images':[url,...], 'reason':str}.
    """
    sku = str(sku).strip()
    if not sku:
        return {"ok": False, "sku": sku, "data": {}, "images": [], "reason": "no SKU"}
    if _use_mock():
        m = mock_data.oskar_media_images(sku, "")
        return {"ok": bool(m.get("images")), "sku": sku, "images": m.get("images", []),
                "data": {"sku": sku, "source": "mock"}, "reason": m.get("reason", "")}
    base = (db.get_setting("oskar_base_url", "https://connect.oskarme.com") or
            "https://connect.oskarme.com").rstrip("/")
    token = db.get_setting("oskar_token", "")
    return _fetch_one(_connect_session(), base, token, sku)


def _fetch_stock_one(sess, base: str, token: str, sku: str, timeout: int = 30) -> dict:
    """Stock qty for ONE SKU from connect's product list (GET /product/list?search=<sku>).
    Matches the row whose 'sku' equals the lookup value. Returns {'ok','sku','qty','reason'}."""
    headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    if token:
        headers["Authorization"] = token
    try:
        r = sess.get(f"{base}/api/v1/product/list", params={"search": sku},
                     headers=headers, timeout=timeout)
        if r.status_code == 401:
            return {"ok": False, "sku": sku, "qty": "",
                    "reason": "unauthorized — refresh oskar token in Settings"}
        r.raise_for_status()
        data = (r.json() or {}).get("data") or []
        low = str(sku).strip().lower()
        match = next((d for d in data if str(d.get("sku", "")).strip().lower() == low), None)
        if match is None and len(data) == 1:   # single result → take it
            match = data[0]
        if match is None:
            return {"ok": True, "sku": sku, "qty": "", "brand": "", "reason": "no exact SKU match"}
        return {"ok": True, "sku": sku, "qty": match.get("qty", ""),
                "brand": match.get("brand", ""), "reason": ""}
    except Exception as e:
        return {"ok": False, "sku": sku, "qty": "", "brand": "", "reason": f"connect error: {e}"}


def fetch_stock_bulk(skus, max_workers: int = 12, timeout: int = 30) -> dict:
    """Stock qty for many SKUs from connect, CONCURRENTLY → {sku: {'ok','qty',...}}.
    Uses the fast product-list/search endpoint (not the heavy combined-media one)."""
    skus = [str(s).strip() for s in (skus or []) if str(s).strip()]
    out: dict = {}
    if not skus:
        return out
    if _use_mock():
        # mock: derive a stable pseudo-qty so the column isn't empty in demo mode
        return {s: {"ok": True, "sku": s, "qty": (abs(hash(s)) % 200) + 1,
                    "brand": "MockBrand", "reason": ""}
                for s in skus}
    base = (db.get_setting("oskar_base_url", "https://connect.oskarme.com") or
            "https://connect.oskarme.com").rstrip("/")
    token = db.get_setting("oskar_token", "")
    sess = _connect_session()
    from concurrent.futures import ThreadPoolExecutor, as_completed
    workers = max(1, min(max_workers, len(skus)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_stock_one, sess, base, token, s, timeout): s for s in skus}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                out[s] = fut.result()
            except Exception as e:
                out[s] = {"ok": False, "sku": s, "qty": "", "reason": str(e)}
    return out


def fetch_products_bulk(skus, max_workers: int = 12, timeout: int = 12) -> dict:
    """Fetch many SKUs from connect CONCURRENTLY → {sku: result}. Settings are read
    ONCE; requests run in a thread pool over a pooled session, so N lookups take
    ~N/workers round-trips instead of N sequential ones."""
    skus = [str(s).strip() for s in (skus or []) if str(s).strip()]
    out: dict = {}
    if not skus:
        return out
    if _use_mock():
        return {s: fetch_product_info(s) for s in skus}
    base = (db.get_setting("oskar_base_url", "https://connect.oskarme.com") or
            "https://connect.oskarme.com").rstrip("/")
    token = db.get_setting("oskar_token", "")
    sess = _connect_session()
    from concurrent.futures import ThreadPoolExecutor, as_completed
    workers = max(1, min(max_workers, len(skus)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one, sess, base, token, s, timeout): s for s in skus}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                out[s] = fut.result()
            except Exception as e:
                out[s] = {"ok": False, "sku": s, "data": {}, "images": [], "reason": str(e)}
    return out


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
