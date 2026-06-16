"""
core/sp_api.py
==============
REAL Amazon Selling Partner API (SP-API) client implementing the documented
listing-creation flow for Amazon.ae / .sa (EU endpoint):

  Auth        -> LWA  POST https://api.amazon.com/auth/o2/token
  Find type   -> Product Type Definitions 2020-09-01  searchDefinitionsProductTypes
  Get schema  -> Product Type Definitions 2020-09-01  getDefinitionsProductType + schema URL
  Catalog     -> Catalog Items 2022-04-01  searchCatalogItems (does the ASIN already exist?)
  Validate    -> Listings Items 2021-08-01  putListingsItem (mode=VALIDATION_PREVIEW, no commit)
  Submit      -> Feeds 2021-06-30  JSON_LISTINGS_FEED
                 createFeedDocument -> upload -> createFeed -> getFeed (poll) -> getFeedDocument

Modern SP-API needs only an LWA access token in 'x-amz-access-token' (no AWS SigV4).
Credentials come from Settings (SQLite). Functions accept FLAT attribute dicts and
map them to SP-API's nested shape via to_sp_attributes().
"""

from __future__ import annotations
import time

from core import db

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
REGION_ENDPOINTS = {
    "eu": "https://sellingpartnerapi-eu.amazon.com",
    "na": "https://sellingpartnerapi-na.amazon.com",
    "fe": "https://sellingpartnerapi-fe.amazon.com",
}
_TOKEN_CACHE: dict = {}
# product_type -> set of attribute names that type's schema defines. Lets the
# attribute mapper emit dimensions/weights under the name THIS type actually uses
# (e.g. item_dimensions vs item_length_width_height) instead of one hardcoded guess.
_PT_ATTR_CACHE: dict = {}
_SESSION = None


def _sess():
    """A shared requests.Session with connection pooling + automatic retries on
    transient network/5xx errors (so a dropped TLS connection doesn't fail a call)."""
    global _SESSION
    if _SESSION is None:
        import requests
        from requests.adapters import HTTPAdapter
        try:
            from urllib3.util.retry import Retry
            retry = Retry(total=4, connect=4, read=4, backoff_factor=1.0,
                          status_forcelist=[429, 500, 502, 503, 504],
                          allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE"]),
                          raise_on_status=False)
            adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
        except Exception:
            adapter = HTTPAdapter()
        s = requests.Session()
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSION = s
    return _SESSION


def _http(method: str, url: str, **kwargs):
    """Session request wrapped in an explicit retry loop. Catches transient SSL
    EOF / connection / timeout errors (which urllib3 doesn't always retry) and
    backs off, so a flaky network or TLS-inspecting antivirus doesn't crash a call."""
    import requests
    transient = (requests.exceptions.SSLError, requests.exceptions.ConnectionError,
                 requests.exceptions.Timeout, requests.exceptions.ChunkedEncodingError)
    last = None
    for attempt in range(4):
        try:
            return _sess().request(method, url, **kwargs)
        except transient as e:
            last = e
            time.sleep(1.0 * (attempt + 1))
    raise last


# Common country names → ISO-3166 alpha-2 (Amazon country_of_origin needs codes).
_COUNTRY_ISO = {
    "china": "CN", "uae": "AE", "united arab emirates": "AE", "usa": "US",
    "united states": "US", "india": "IN", "japan": "JP", "germany": "DE",
    "uk": "GB", "united kingdom": "GB", "south korea": "KR", "korea": "KR",
    "taiwan": "TW", "vietnam": "VN", "thailand": "TH", "malaysia": "MY",
    "indonesia": "ID", "hong kong": "HK", "singapore": "SG", "france": "FR",
    "italy": "IT", "spain": "ES", "turkey": "TR", "saudi arabia": "SA",
}


def creds() -> dict:
    region = db.get_setting("amazon_region", "eu") or "eu"
    return {
        "client_id": db.get_setting("amazon_lwa_client_id", ""),
        "client_secret": db.get_setting("amazon_lwa_client_secret", ""),
        "refresh_token": db.get_setting("amazon_refresh_token", ""),
        "marketplace_id": db.get_setting("amazon_marketplace_id", "A2VIGQ35RCS4UG"),
        "seller_id": db.get_setting("amazon_seller_id", ""),
        "endpoint": REGION_ENDPOINTS.get(region, REGION_ENDPOINTS["eu"]),
        "issue_locale": db.get_setting("amazon_issue_locale", "en_US") or "en_US",
    }


def configured() -> bool:
    c = creds()
    return all([c["client_id"], c["client_secret"], c["refresh_token"]])


def access_token() -> str:
    import requests
    c = creds()
    if not configured():
        raise RuntimeError("SP-API credentials are incomplete (Settings → AI & Amazon).")
    now = time.time()
    cached = _TOKEN_CACHE.get(c["refresh_token"])
    if cached and cached[1] > now + 30:
        return cached[0]
    resp = _http("post", LWA_TOKEN_URL, data={
        "grant_type": "refresh_token", "refresh_token": c["refresh_token"],
        "client_id": c["client_id"], "client_secret": c["client_secret"],
    }, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"LWA token error {resp.status_code}: {resp.text[:200]}")
    j = resp.json()
    token = j["access_token"]
    _TOKEN_CACHE[c["refresh_token"]] = (token, now + int(j.get("expires_in", 3600)))
    return token


def _headers(extra: dict | None = None) -> dict:
    h = {"x-amz-access-token": access_token(), "content-type": "application/json"}
    if extra:
        h.update(extra)
    return h


def test_connection() -> tuple[bool, str]:
    try:
        access_token()
        return True, "✓ LWA token obtained — credentials valid."
    except Exception as e:
        return False, f"✗ {e}"


# ---------------------------------------------------------------------------
# Product Type Definitions 2020-09-01
# ---------------------------------------------------------------------------
def search_product_types(keywords: str = "") -> list[str]:
    import requests
    c = creds()
    params = {"marketplaceIds": c["marketplace_id"]}
    if keywords:
        params["keywords"] = keywords
    r = _http("get", f"{c['endpoint']}/definitions/2020-09-01/productTypes",
                     params=params, headers=_headers(), timeout=20)
    r.raise_for_status()
    return [pt["name"] for pt in r.json().get("productTypes", [])]


def _leaf_value_schema(prop: dict) -> dict:
    cur = prop
    if cur.get("type") == "array":
        cur = cur.get("items", {})
    props = cur.get("properties", {})
    return props.get("value", cur)


def _parse_schema(schema: dict) -> list[dict]:
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields = []
    for name in sorted(props, key=lambda n: (n not in required, n)):
        p = props[name]
        leaf = _leaf_value_schema(p)
        ftype, options = "text", None
        enum = leaf.get("enum") or (leaf.get("items", {}) or {}).get("enum")
        is_int = leaf.get("type") == "integer"
        is_bool = leaf.get("type") == "boolean" or (
            bool(enum) and all(isinstance(e, bool) for e in enum))
        if enum:
            ftype, options = "select", list(enum)
        elif leaf.get("type") in ("number", "integer"):
            ftype = "number"
        elif leaf.get("maxLength", 0) and leaf["maxLength"] > 120:
            ftype = "textarea"
        fields.append({"name": name, "label": p.get("title", name).strip() or name,
                       "required": name in required, "type": ftype, "options": options,
                       "max": leaf.get("maxLength"), "integer": is_int, "boolean": is_bool})
    return fields


def get_requirements(product_type: str) -> list[dict]:
    import requests
    c = creds()
    r = _http("get", f"{c['endpoint']}/definitions/2020-09-01/productTypes/{product_type}",
                     params={"marketplaceIds": c["marketplace_id"], "requirements": "LISTING",
                             "locale": "DEFAULT", "sellerId": c["seller_id"]},
                     headers=_headers(), timeout=25)
    r.raise_for_status()
    meta = r.json()
    schema_url = meta["schema"]["link"]["resource"]
    sch = _http("get", schema_url, timeout=25).json()   # pre-signed URL, no auth
    return _parse_schema(sch)


# ---------------------------------------------------------------------------
# Catalog Items 2022-04-01 — does the product already exist?
# ---------------------------------------------------------------------------
def search_catalog_items(identifier: str, id_type: str = "GTIN") -> list[dict]:
    import requests
    c = creds()
    r = _http("get", f"{c['endpoint']}/catalog/2022-04-01/items",
                     params={"marketplaceIds": c["marketplace_id"],
                             "identifiers": str(identifier), "identifiersType": id_type,
                             "includedData": "identifiers,summaries,productTypes"},
                     headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json().get("items", [])


def get_item_by_asin(asin: str) -> dict:
    """Fetch one ASIN's catalog record (Catalog Items 2022-04-01 getCatalogItem).
    Returns {ok, asin, title, brand, product_type, attributes, reason}. `attributes`
    is Amazon's catalog attribute dict (may carry battery info when present)."""
    import requests
    asin = str(asin).strip().upper()
    if not asin:
        return {"ok": False, "asin": asin, "reason": "empty ASIN"}
    c = creds()
    try:
        r = _http("get", f"{c['endpoint']}/catalog/2022-04-01/items/{asin}",
                  params={"marketplaceIds": c["marketplace_id"],
                          "includedData": "summaries,attributes,productTypes"},
                  headers=_headers(), timeout=20)
        if r.status_code == 404:
            return {"ok": False, "asin": asin, "reason": "ASIN not found in this marketplace"}
        r.raise_for_status()
        j = r.json()
        summ = (j.get("summaries") or [{}])[0]
        pts = j.get("productTypes") or [{}]
        return {"ok": True, "asin": asin,
                "title": summ.get("itemName", ""), "brand": summ.get("brand", ""),
                "product_type": (pts[0].get("productType") if pts else "") or "",
                "attributes": j.get("attributes", {}) or {}, "reason": ""}
    except Exception as e:
        return {"ok": False, "asin": asin, "reason": f"lookup error: {e}"}


def _derive_amazon_status(statuses: set, all_issues: list, offers_present: bool,
                          qty) -> str:
    """Map raw SP-API signals to the seller-facing status the user sees in Seller
    Central: Active / Out of stock / Missing offer / Missing information /
    Search suppressed / Suppressed / Inactive."""
    actions = set()
    for i in all_issues or []:
        for a in i.get("enforcements", []) or []:
            actions.add(a)
    if "SEARCH_SUPPRESSED" in actions:
        return "Search suppressed"
    if any(a in actions for a in ("LISTING_SUPPRESSED", "CATALOG_ITEM_REMOVED")):
        return "Suppressed"
    if any(i.get("severity") == "ERROR" for i in (all_issues or [])):
        return "Missing information"
    if "BUYABLE" in statuses:
        if qty is not None and qty <= 0:
            return "Out of stock"
        return "Active"
    # Discoverable in the catalog but not buyable → no live offer, or zero stock.
    if "DISCOVERABLE" in statuses:
        if not offers_present:
            return "Missing offer"
        if qty is not None and qty <= 0:
            return "Out of stock"
        return "Inactive"
    return "Inactive"


def get_listing_status(sku: str) -> dict:
    """Confirm a listing directly (getListingsItem) and derive its real Amazon status.

    Returns {exists, status, amazon_status, status_list, asin, issues, all_issues}.
    `amazon_status` is the seller-facing state (Active / Out of stock / Missing offer /
    Missing information / Search suppressed / …). `status` is the raw BUYABLE/DISCOVERABLE
    string. A created listing is usually DISCOVERABLE within seconds of submission.
    """
    import requests
    c = creds()
    url = (f"{c['endpoint']}/listings/2021-08-01/items/{c['seller_id']}/"
           f"{requests.utils.quote(str(sku), safe='')}")
    r = _http("get", url, params={"marketplaceIds": c["marketplace_id"],
                                  "includedData": "summaries,offers,fulfillmentAvailability,issues",
                                  "issueLocale": c["issue_locale"]},
                     headers=_headers(), timeout=20)
    if r.status_code == 404:
        return {"exists": False, "status": "", "amazon_status": "Not on Amazon",
                "status_list": [], "asin": "", "issues": [], "all_issues": []}
    r.raise_for_status()
    j = r.json()
    summ = (j.get("summaries") or [{}])[0]
    status_list = summ.get("status") or []
    if isinstance(status_list, str):
        status_list = [status_list]
    # Keep EVERY issue (not just blocking errors): Amazon reports missing/incomplete
    # information as WARNING severity — that's the "listing is missing info" the seller
    # sees. Each carries the attribute name(s) and any enforcement (e.g. SEARCH_SUPPRESSED).
    all_issues = [{"severity": i.get("severity", ""), "message": i.get("message", ""),
                   "attributes": i.get("attributeNames", []) or [],
                   "code": i.get("code", ""),
                   "enforcements": [a.get("action") for a in
                                    ((i.get("enforcements", {}) or {}).get("actions", []) or [])
                                    if a.get("action")]}
                  for i in (j.get("issues", []) or [])]
    errs = [i["message"] for i in all_issues if i["severity"] == "ERROR"]
    # Stock signal: sum fulfillmentAvailability quantities when present (FBM, or FBA
    # that reports it). None = unknown (don't claim out-of-stock when we can't tell).
    fa = j.get("fulfillmentAvailability") or []
    qsum, have_q = 0, False
    for f in fa:
        if "quantity" in f:
            qsum += int(f.get("quantity") or 0)
            have_q = True
    qty = qsum if have_q else None
    amazon_status = _derive_amazon_status(set(status_list), all_issues,
                                          bool(j.get("offers")), qty)
    return {"exists": True, "status": ", ".join(status_list),
            "amazon_status": amazon_status, "status_list": status_list,
            "asin": summ.get("asin", ""), "issues": errs, "all_issues": all_issues}


# ---------------------------------------------------------------------------
# Attribute mapping (flat form values -> SP-API nested attributes)
# ---------------------------------------------------------------------------
def defined_attribute_names(product_type: str) -> set:
    """Set of attribute names the product type's schema defines. Cached per
    (product_type, marketplace). Used so dimension/weight attributes are emitted
    under the name THIS type actually uses. Returns an empty set on any failure —
    callers then fall back to the most common modern name."""
    if not product_type:
        return set()
    c = creds()
    key = (product_type, c["marketplace_id"])
    if key not in _PT_ATTR_CACHE:
        try:
            names = {f["name"] for f in get_requirements(product_type)}
        except Exception:
            names = set()
        # Only cache a SUCCESSFUL (non-empty) lookup. Caching an empty result would
        # pin every later push to the fallback name after one transient failure —
        # which silently mis-emits dimensions for the whole session.
        if names:
            _PT_ATTR_CACHE[key] = names
        return names
    return _PT_ATTR_CACHE[key]


def _resolve_attr(defined: set, prefer: list, match=None) -> str | None:
    """Pick the attribute name a product type actually defines for a concept.
    `prefer` = exact names tried in order; `match(name)` = a fuzzy fallback for
    types that name it differently. Returns None when the schema is known but
    nothing matches (caller falls back to its default only when `defined` is empty)."""
    for name in prefer:
        if name in defined:
            return name
    if match:
        for name in defined:
            if match(name):
                return name
    return None


def _emit_dims(out: dict, defined: set, mp: str, l, w, h, unit: str,
               nested_names: list, sep_names: dict, match) -> None:
    """Emit length/width/height under whatever SHAPE this product type defines:

      * nested  — one attribute like {'length':{value,unit}, 'width':…, 'height':…}
                  (e.g. item_dimensions, item_package_dimensions); or
      * separate — three per-axis attributes, each {value, unit} (e.g. package_height,
                  package_width, package_length) — each one needs its own unit, which
                  is what triggers 'Package Height Unit is required but missing'.

    `nested_names` = preferred nested attribute names; `sep_names` = the per-axis
    attribute names {'length':…, 'width':…, 'height':…}; `match` = fuzzy nested-name
    fallback.

    Resolution:
      * schema clearly NESTED  → emit just the nested block;
      * schema clearly SEPARATE → emit just the three per-axis attributes;
      * both defined           → emit both;
      * shape UNIDENTIFIABLE (schema empty/unreadable, or it defines a dimension
        attribute under a name we don't recognise) → SHOTGUN every known
        representation. Amazon's JSON_LISTINGS_FEED ignores attribute names a
        product type doesn't define (a warning, not an error), so whichever name
        the type actually requires gets satisfied and the rest are dropped. This is
        what makes a push succeed without us having to know the exact schema."""
    def _nested(name):
        out[name] = [{"length": {"value": float(l), "unit": unit},
                      "width": {"value": float(w), "unit": unit},
                      "height": {"value": float(h), "unit": unit},
                      "marketplace_id": mp}]

    def _separate(names):
        vals = {"length": l, "width": w, "height": h}
        for axis, nm in names.items():
            out[nm] = [{"value": float(vals[axis]), "unit": unit, "marketplace_id": mp}]

    nested = _resolve_attr(defined, nested_names, match=match)
    sep_present = {axis: nm for axis, nm in sep_names.items() if nm in defined}
    if nested and sep_present:
        _nested(nested)
        _separate(sep_present)
    elif nested:
        _nested(nested)
    elif sep_present:
        _separate(sep_present)
    else:
        # Couldn't identify the shape → cover every representation at once.
        for nm in nested_names:
            _nested(nm)
        _separate(sep_names)


def to_sp_attributes(flat: dict, mp: str, defined: set | None = None) -> dict:
    defined = defined or set()
    special = {"standard_price", "list_price", "quantity", "fulfillment_channel",
               "main_image_url", "other_image_urls",
               "external_product_id", "external_product_id_type",
               "condition_type", "parentage_level", "variation_theme",
               "child_relationship_type", "parent_sku", "color_name", "country_of_origin",
               "shipping_weight", "shipping_weight_unit",
               "item_length", "item_width", "item_height", "dimension_unit",
               "package_weight", "package_weight_unit",
               "package_length", "package_width", "package_height", "package_dimension_unit",
               "battery_cell_composition", "battery_type", "number_of_batteries",
               "battery_weight", "battery_weight_unit", "lithium_energy",
               "lithium_energy_unit", "lithium_packaging", "lithium_weight",
               "lithium_weight_unit",
               "wattage", "wattage_unit", "voltage", "voltage_unit",
               "item_weight", "item_weight_unit",
               "generic_keyword", "generic_keyword_more", "unit_count"}
    is_parent = flat.get("parentage_level") == "parent"
    out: dict = {}
    for k, v in flat.items():
        # Skip blanks and zero-valued optional numbers (e.g. don't send
        # max_order_quantity=0, which Amazon rejects as < 1). NOTE: booleans
        # must pass through — in Python `False == 0`, so a legit False value
        # (e.g. is_assembly_required=False) would otherwise be dropped.
        if k in special or v is None or v == "":
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0:
            continue
        if isinstance(v, str) and "\n" in v:
            out[k] = [{"value": ln.strip(), "marketplace_id": mp}
                      for ln in v.splitlines() if ln.strip()]
        else:
            # Amazon rejects float values (e.g. 1.0) for integer fields like
            # number_of_items / number_of_boxes / number_of_lithium_ion_cells —
            # the editor's number_input always yields floats. Coerce whole-number
            # floats back to int. Genuine decimals (2.5) are preserved. Booleans
            # pass through untouched.
            if isinstance(v, float) and not isinstance(v, bool) and v.is_integer():
                v = int(v)
            out[k] = [{"value": v, "marketplace_id": mp}]
    if flat.get("condition_type"):
        out["condition_type"] = [{"value": flat["condition_type"], "marketplace_id": mp}]
    # Country of origin must be an ISO-3166 alpha-2 code (e.g. CN), not a name.
    if flat.get("country_of_origin"):
        cv = str(flat["country_of_origin"]).strip()
        iso = _COUNTRY_ISO.get(cv.lower(), cv.upper() if len(cv) == 2 else cv)
        out["country_of_origin"] = [{"value": iso, "marketplace_id": mp}]

    # --- variation relationship attributes ---
    if flat.get("parentage_level"):
        out["parentage_level"] = [{"value": flat["parentage_level"], "marketplace_id": mp}]
    if flat.get("variation_theme"):
        # variation_theme uses a 'name' field, not 'value'.
        out["variation_theme"] = [{"name": flat["variation_theme"], "marketplace_id": mp}]
    # Child → parent linkage for a variation family.
    if flat.get("parent_sku"):
        out["child_parent_sku_relationship"] = [{
            "child_relationship_type": "variation",
            "parent_sku": str(flat["parent_sku"]), "marketplace_id": mp}]
    if flat.get("color_name"):
        out["color_name"] = [{"value": flat["color_name"], "marketplace_id": mp}]

    # --- offer attributes (skip entirely for a parent — it has no buyable offer) ---
    if not is_parent:
        if flat.get("standard_price"):
            price = float(flat["standard_price"])
            # List Price (RRP / strikethrough) — tax-inclusive in UAE.
            out["list_price"] = [{"currency": "AED", "value_with_tax": price,
                                  "marketplace_id": mp}]
            # Your Price (the actual buyable offer) — set EQUAL to the list price.
            out["purchasable_offer"] = [{
                "currency": "AED", "marketplace_id": mp,
                "our_price": [{"schedule": [{"value_with_tax": price}]}]}]
        if flat.get("external_product_id"):
            out["externally_assigned_product_identifier"] = [{
                "value": str(flat["external_product_id"]),
                "type": (flat.get("external_product_id_type") or "ean").lower(),
                "marketplace_id": mp}]
        channel = flat.get("fulfillment_channel", "FBM")
        if channel == "FBA":
            # Amazon-fulfilled (AFN). UAE is served by the SP-API EU region, whose
            # only approved Amazon-fulfilled code is AMAZON_EU.
            out["fulfillment_availability"] = [{"fulfillment_channel_code": "AMAZON_EU"}]
        else:
            out["fulfillment_availability"] = [{"fulfillment_channel_code": "DEFAULT",
                                                "quantity": int(float(flat.get("quantity", 1) or 1))}]
    # Power specs as {value, unit} (Amazon requires the unit alongside the number).
    if flat.get("wattage") not in (None, "", 0):
        out["wattage"] = [{"value": float(flat["wattage"]),
                           "unit": flat.get("wattage_unit", "watts"), "marketplace_id": mp}]
    if flat.get("voltage") not in (None, "", 0):
        out["voltage"] = [{"value": float(flat["voltage"]),
                           "unit": flat.get("voltage_unit", "volts"), "marketplace_id": mp}]
    # Unit Count = {value, type:{value, language_tag}} — 'Count' for unit items.
    if flat.get("unit_count") not in (None, "", 0):
        out["unit_count"] = [{"value": float(flat["unit_count"]),
                              "type": {"value": "count", "language_tag": "en_AE"},
                              "marketplace_id": mp}]
    # Net product weight as {value, unit}.
    if flat.get("item_weight") not in (None, "", 0):
        out["item_weight"] = [{"value": float(flat["item_weight"]),
                               "unit": flat.get("item_weight_unit", "kilograms"),
                               "marketplace_id": mp}]
    # Generic Keywords: send a SINGLE ≤500-char value. Some product types allow
    # only one occurrence (others allow many) — one value is safe for ALL types
    # and Amazon indexes the whole semicolon string for search.
    gk = (str(flat.get("generic_keyword") or "").strip()
          or str(flat.get("generic_keyword_more") or "").strip())
    if gk:
        out["generic_keyword"] = [{"value": gk[:500], "marketplace_id": mp}]
    if flat.get("main_image_url"):
        out["main_product_image_locator"] = [{"media_location": flat["main_image_url"],
                                              "marketplace_id": mp}]
    # Additional product images (lifestyle/detail/packaging) → other_product_image_locator_1..8.
    for idx, url in enumerate(flat.get("other_image_urls") or [], start=1):
        if idx > 8 or not str(url).startswith("http"):
            continue
        out[f"other_product_image_locator_{idx}"] = [{"media_location": url,
                                                      "marketplace_id": mp}]
    # Shipping weight (value + unit).
    if flat.get("shipping_weight"):
        out["website_shipping_weight"] = [{"value": float(flat["shipping_weight"]),
                                           "unit": flat.get("shipping_weight_unit", "kilograms"),
                                           "marketplace_id": mp}]
    # Item dimensions — emitted under whatever NAME *and* SHAPE this product type
    # defines (nested item_dimensions / item_length_width_height, or separate
    # item_length/width/height each with its own unit), so the unit isn't flagged as
    # 'Item length Unit is required but missing'.
    if flat.get("item_length") and flat.get("item_width") and flat.get("item_height"):
        u = flat.get("dimension_unit", "centimeters")
        _emit_dims(out, defined, mp, flat["item_length"], flat["item_width"],
                   flat["item_height"], u,
                   nested_names=["item_dimensions", "item_length_width_height"],
                   sep_names={"length": "item_length", "width": "item_width",
                              "height": "item_height"},
                   match=lambda x: x.lower().startswith("item")
                   and ("dimension" in x.lower() or "length_width_height" in x.lower())
                   and "package" not in x.lower() and "display" not in x.lower())
    # Package weight (value + unit).
    if flat.get("package_weight"):
        out["item_package_weight"] = [{"value": float(flat["package_weight"]),
                                       "unit": flat.get("package_weight_unit", "kilograms"),
                                       "marketplace_id": mp}]
    # Package dimensions — same name+shape resolution. Many types (e.g. ELECTRIC_FAN)
    # use SEPARATE package_height/width/length attributes, each requiring its own
    # unit → 'Package Height Unit is required but missing' when sent as one block.
    if flat.get("package_length") and flat.get("package_width") and flat.get("package_height"):
        u = flat.get("package_dimension_unit", "centimeters")
        _emit_dims(out, defined, mp, flat["package_length"], flat["package_width"],
                   flat["package_height"], u,
                   nested_names=["item_package_dimensions", "package_dimensions"],
                   sep_names={"length": "package_length", "width": "package_width",
                              "height": "package_height"},
                   match=lambda x: "package" in x.lower()
                   and ("dimension" in x.lower() or "length_width_height" in x.lower()))
    # Battery info (for battery-powered products).
    if flat.get("battery_cell_composition"):
        b = {"cell_composition": [{"value": flat["battery_cell_composition"]}],
             "marketplace_id": mp}
        if flat.get("battery_weight"):
            b["weight"] = [{"value": float(flat["battery_weight"]),
                            "unit": flat.get("battery_weight_unit", "kilograms")}]
        out["battery"] = [b]
    if flat.get("battery_type"):
        out["num_batteries"] = [{"quantity": int(float(flat.get("number_of_batteries", 1) or 1)),
                                 "type": flat["battery_type"], "marketplace_id": mp}]
    # Lithium battery details (required once cell composition is lithium_*).
    if flat.get("lithium_energy") or flat.get("lithium_packaging"):
        lb = {"marketplace_id": mp}
        if flat.get("lithium_energy"):
            lb["energy_content"] = [{"value": float(flat["lithium_energy"]),
                                     "unit": flat.get("lithium_energy_unit", "watt_hours")}]
        if flat.get("lithium_packaging"):
            lb["packaging"] = [{"value": flat["lithium_packaging"]}]
        if flat.get("lithium_weight"):
            lb["weight"] = [{"value": float(flat["lithium_weight"]),
                             "unit": flat.get("lithium_weight_unit", "kilograms")}]
        out["lithium_battery"] = [lb]
    return out


# ---------------------------------------------------------------------------
# Listings Items 2021-08-01 — VALIDATION_PREVIEW (validate, no commit)
# ---------------------------------------------------------------------------
def validate_preview(sku: str, product_type: str, flat_attributes: dict) -> dict:
    import requests
    c = creds()
    body = {"productType": product_type, "requirements": "LISTING",
            "attributes": to_sp_attributes(flat_attributes, c["marketplace_id"],
                                           defined_attribute_names(product_type))}
    url = (f"{c['endpoint']}/listings/2021-08-01/items/{c['seller_id']}/"
           f"{requests.utils.quote(str(sku), safe='')}")
    r = _http("put", url, params={"marketplaceIds": c["marketplace_id"],
                                  "issueLocale": c["issue_locale"], "mode": "VALIDATION_PREVIEW"},
                     headers=_headers(), json=body, timeout=30)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:400]}
    issues = list(j.get("issues", []))
    # On a 4xx the Listings API returns top-level `errors` (code/message/details),
    # NOT `issues`. Fold them in (as ERROR severity) so the UI shows the reason
    # instead of an empty result.
    for e in j.get("errors", []) or []:
        issues.append({"severity": "ERROR", "code": e.get("code", ""),
                       "message": e.get("message", str(e))})
    errors = [i for i in issues if i.get("severity") == "ERROR"]
    return {"ok": j.get("status") == "VALID" or (r.status_code in (200, 202) and not errors),
            "http": r.status_code, "status": j.get("status"),
            "issues": issues, "errors": errors}


# ---------------------------------------------------------------------------
# Feeds 2021-06-30 — JSON_LISTINGS_FEED (the actual submission)
# ---------------------------------------------------------------------------
def build_listings_feed(items: list[dict]) -> dict:
    """items: [{sku, product_type, attributes(flat), requirements?}]."""
    c = creds()
    mp = c["marketplace_id"]
    messages = []
    for i, it in enumerate(items, start=1):
        pt = it.get("product_type", "PRODUCT")
        messages.append({
            "messageId": i, "sku": it["sku"], "operationType": "UPDATE",
            "productType": pt,
            "requirements": it.get("requirements", "LISTING"),
            "attributes": to_sp_attributes(it.get("attributes", {}), mp,
                                           defined_attribute_names(pt)),
        })
    return {"header": {"sellerId": c["seller_id"], "version": "2.0",
                       "issueLocale": c["issue_locale"]},
            "messages": messages}


def _create_feed_document() -> dict:
    import requests
    c = creds()
    r = _http("post", f"{c['endpoint']}/feeds/2021-06-30/documents",
                      headers=_headers(), json={"contentType": "application/json; charset=UTF-8"},
                      timeout=20)
    r.raise_for_status()
    return r.json()  # {feedDocumentId, url}


def _upload_feed(url: str, content: bytes) -> None:
    import requests
    up = _http("put", url, data=content,
                      headers={"Content-Type": "application/json; charset=UTF-8"}, timeout=40)
    up.raise_for_status()


def _create_feed(feed_document_id: str) -> str:
    import requests
    c = creds()
    r = _http("post", f"{c['endpoint']}/feeds/2021-06-30/feeds", headers=_headers(),
                      json={"feedType": "JSON_LISTINGS_FEED",
                            "marketplaceIds": [c["marketplace_id"]],
                            "inputFeedDocumentId": feed_document_id}, timeout=20)
    r.raise_for_status()
    return r.json()["feedId"]


def _get_feed(feed_id: str) -> dict:
    import requests
    c = creds()
    r = _http("get", f"{c['endpoint']}/feeds/2021-06-30/feeds/{feed_id}",
                     headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def _get_feed_document(doc_id: str) -> dict:
    import requests
    c = creds()
    r = _http("get", f"{c['endpoint']}/feeds/2021-06-30/documents/{doc_id}",
                     headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def submit_listings_feed(items: list[dict], poll_timeout: int = 150) -> dict:
    """Full JSON_LISTINGS_FEED submission. Returns a normalized result dict."""
    import json as _json
    import requests
    feed = build_listings_feed(items)
    content = _json.dumps(feed).encode("utf-8")
    sku_by_msg = {m["messageId"]: m["sku"] for m in feed["messages"]}

    doc = _create_feed_document()
    _upload_feed(doc["url"], content)
    feed_id = _create_feed(doc["feedDocumentId"])

    status, result_doc = "IN_QUEUE", None
    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        g = _get_feed(feed_id)
        status = g.get("processingStatus", "IN_PROGRESS")
        if status in ("DONE", "FATAL", "CANCELLED"):
            result_doc = g.get("resultFeedDocumentId")
            break
        time.sleep(4)

    report = None
    if result_doc:
        d = _get_feed_document(result_doc)
        rep = _http("get", d["url"], timeout=30)
        raw = rep.content
        if d.get("compressionAlgorithm") == "GZIP":
            import gzip
            raw = gzip.decompress(raw)
        try:
            report = _json.loads(raw.decode("utf-8"))
        except Exception:
            report = {"raw": raw[:500].decode("utf-8", "ignore")}

    return _normalize_feed_result(feed_id, status, report, sku_by_msg)


# ---------------------------------------------------------------------------
# Orders API 2021 (v0) — real sales
# ---------------------------------------------------------------------------
def get_orders_raw(days: int = 30, max_orders: int = 60) -> list:
    import requests
    from datetime import datetime, timedelta, timezone
    c = creds()
    after = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    orders, token = [], None
    while len(orders) < max_orders:
        params = ({"MarketplaceIds": c["marketplace_id"], "NextToken": token} if token
                  else {"MarketplaceIds": c["marketplace_id"], "CreatedAfter": after})
        r = _http("get", c["endpoint"] + "/orders/v0/orders", params=params,
                         headers=_headers(), timeout=30)
        r.raise_for_status()
        pl = r.json().get("payload", {})
        orders.extend(pl.get("Orders", []))
        token = pl.get("NextToken")
        if not token:
            break
    return orders[:max_orders]


# ---------------------------------------------------------------------------
# FBA Inventory API v1 — real Amazon-warehouse stock
# ---------------------------------------------------------------------------
def get_fba_inventory_raw() -> list:
    import requests
    c = creds()
    r = _http("get", c["endpoint"] + "/fba/inventory/v1/summaries",
                     params={"details": "true", "granularityType": "Marketplace",
                             "granularityId": c["marketplace_id"],
                             "marketplaceIds": c["marketplace_id"]},
                     headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json().get("payload", {}).get("inventorySummaries", [])


def _normalize_feed_result(feed_id, status, report, sku_by_msg) -> dict:
    terminal = status in ("DONE", "FATAL", "CANCELLED")
    # If the feed hasn't finished OR we couldn't read the processing report, we
    # genuinely don't know yet — report 'submitted' (pending), NOT 'accepted'.
    if not terminal or report is None:
        per_sku = {sku: {"status": "submitted", "issues": []}
                   for sku in sku_by_msg.values()}
        return {"mode": "live", "feedId": feed_id, "processingStatus": status,
                "accepted": 0, "rejected": 0, "submitted": len(per_sku),
                "per_sku": per_sku, "report": report}

    per_sku = {sku: {"status": "accepted", "issues": []} for sku in sku_by_msg.values()}
    for issue in report.get("issues", []):
        sku = sku_by_msg.get(issue.get("messageId"))
        if sku and issue.get("severity") == "ERROR":
            per_sku[sku]["status"] = "rejected"
            per_sku[sku]["issues"].append(issue.get("message", ""))
    accepted = sum(1 for v in per_sku.values() if v["status"] == "accepted")
    rejected = sum(1 for v in per_sku.values() if v["status"] == "rejected")
    return {"mode": "live", "feedId": feed_id, "processingStatus": status,
            "accepted": accepted, "rejected": rejected, "submitted": 0,
            "per_sku": per_sku, "report": report}
