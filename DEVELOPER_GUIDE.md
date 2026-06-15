# 🛠️ Developer Guide — Amazon.ae Seller Dashboard

This is the **complete, self-contained reference** for editing the app and wiring
real APIs. You do not need any chat history — everything you need is here and in
the code comments. Keep this file with the project.

---

## 0. The golden rules of this codebase

1. **Every Amazon call goes through `core/api_client.py`.** The UI never calls
   Amazon directly. To go live, you only edit that one file (+ paste credentials
   in Settings). The UI keeps working unchanged.
2. **Every durable thing is in SQLite via `core/db.py`.** Settings, secrets,
   tasks, price history, catalog, chat — all there. Nothing important lives in
   memory.
3. **Secrets are entered in the Settings page (⚙️), not hard-coded.** They're
   saved into `data/seller.db`. Mock/live is a toggle per connector.
4. **Mock data lives in `core/mock_data.py`.** Each real API method must return
   the **same column shape** as its mock so the UI doesn't break — the shapes are
   documented in section 4 below.

---

## 1. Run / restart (Windows PowerShell)

```powershell
cd "C:\Users\Admin\Desktop\New folder\seller_dashboard"
# first time only:
python -m venv venv ; .\venv\Scripts\Activate.ps1 ; pip install -r requirements.txt
# every time:
.\venv\Scripts\Activate.ps1 ; streamlit run app.py
```
Login: `admin` / `your local password`. Stop with `Ctrl + C` in the terminal.

---

## 2. Where to make common changes

| I want to… | File / place |
|---|---|
| Wire a real Amazon API | `core/api_client.py` (find the method, replace the `TODO`) |
| Connect my inventory website | Settings → URL+token, then `core/inventory_source.py::fetch_inventory()` |
| Wire connect.oskarme.com | Settings → URL+token, then `core/oskar_source.py` |
| Enable the live AI assistant | Settings → paste Anthropic key (model in `core/assistant.py::MODEL`) |
| Turn on email/Telegram alerts | Settings → Notifications tab |
| Change mock numbers/items | `core/mock_data.py` |
| Restyle the look | `core/styles.py` (colors in `PALETTE`, CSS in `inject_global_css`) |
| Add a brand/category stock rule | In-app: Stock Management → Stock Configuration |
| Add a whole new page | `modules/<name>.py` + register in `app.py::PAGES` (section 6) |
| Change the login password | `core/auth.py` (section 7) |
| Adjust file column auto-detection | `core/util.py` → `_FIELD_ALIASES` |

---

## 3. Settings keys the app reads (all stored in `data/seller.db`)

These are the exact `db.get_setting(...)` keys. The Settings page writes them;
you can also set them programmatically with `db.set_setting(key, value)`.

| Key | Meaning |
|---|---|
| `use_mock_amazon` | "1" = mock, "0" = live SP-API/Ads |
| `use_mock_inventory` | "1" = mock inventory site, "0" = live |
| `use_mock_oskar` | "1" = mock enrichment, "0" = live |
| `inventory_base_url`, `inventory_auth_token` | your inventory website |
| `oskar_base_url`, `oskar_token` | connect.oskarme.com |
| `anthropic_api_key` | enables live Claude assistant |
| `amazon_lwa_client_id`, `amazon_lwa_client_secret`, `amazon_refresh_token` | SP-API LWA auth |
| `amazon_marketplace_id` | UAE = `A2VIGQ35RCS4UG` |
| `amazon_ads_profile_id` | Amazon Ads profile |
| `channel_email`, `channel_telegram` | "1" to enable that channel |
| `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_from`, `smtp_to` | email |
| `telegram_bot_token`, `telegram_chat_id` | Telegram |
| `notify_on_out_of_stock`, `notify_on_lost_buybox`, `notify_on_budget`, `notify_on_daily_tasks` | per-event triggers |

---

## 4. Data shapes each `api_client` method MUST return

When you replace a mock with a real call, return a pandas DataFrame with **these
exact column names** (extra columns are fine; missing ones break the UI).

```
get_my_listings()        -> sku, asin, title, brand, category, fba_stock, daily_velocity, price
get_top_sellers_in_category(category) -> title, keywords, price
get_fees_estimate(asin, price) -> dict: referral_fee, fba_fee, closing_fee, total_fees
get_lost_buybox()        -> sku, title, your_price, buybox_price, buybox_winner
get_campaigns()          -> campaign, spend_today, avg_daily, impressions, clicks, acos, sales
get_keyword_targets(item)-> keyword, current_bid, suggested_bid, acos, action
create_campaign(payload) -> dict: status, campaign
get_deal_suggestions()   -> item, current_price, suggested_deal_price, deal_type, margin_pct
get_market_comparison()  -> item, your_price, market_min, monthly_demand, trend, signal
get_fba_inventory()      -> sku, title, fba_units, daily_velocity, days_in_fba
get_events()             -> date, event, action
get_orders()             -> order_id, date, item, qty, status, revenue, cost, ad_spend
push_listing(listing)    -> dict: status, sku
```

Inventory website (`inventory_source.fetch_inventory()`):
```
-> (DataFrame[sku, title, brand, category, warehouse_qty, cost], status_message)
```

---

## 5. Wiring real APIs — concrete starting code

> Install the SDKs first (already in requirements except the Amazon ones):
> ```powershell
> pip install python-amazon-sp-api requests
> ```

### 5a. SP-API — listings, orders, fees, pricing, FBA
The community library `python-amazon-sp-api` is the fastest path. In
`core/api_client.py`, replace a `TODO` like this:

```python
# top of api_client.py
from sp_api.api import Orders, CatalogItems, Inventories, ProductFees, Products
from sp_api.base import Marketplaces

def _spapi_credentials(self):
    c = self._credentials()
    return dict(
        refresh_token=c["lwa_client_id"] and c["refresh_token"],
        lwa_app_id=c["lwa_client_id"],
        lwa_client_secret=c["lwa_client_secret"],
    )

def get_orders(self):
    if self.use_mock:
        return mock_data.orders()
    creds = self._spapi_credentials()
    res = Orders(credentials=creds, marketplace=Marketplaces.AE).get_orders(
        CreatedAfter="2024-01-01T00:00:00Z")
    rows = []
    for o in res.payload.get("Orders", []):
        rows.append({
            "order_id": o["AmazonOrderId"], "date": o["PurchaseDate"][:10],
            "item": o.get("OrderType", ""), "qty": o.get("NumberOfItemsShipped", 0),
            "status": o["OrderStatus"],
            "revenue": float(o.get("OrderTotal", {}).get("Amount", 0)),
            "cost": 0, "ad_spend": 0,   # fill from your own cost table + Ads API
        })
    return pd.DataFrame(rows)
```
- Marketplace for UAE: `Marketplaces.AE` (id `A2VIGQ35RCS4UG`).
- Listings report: use `Reports` API `GET_MERCHANT_LISTINGS_ALL_DATA`, or
  `CatalogItems`. Map to the columns in section 4.
- Fees: `ProductFees(...).get_product_fees_estimate_for_asin(asin, price=...)`.
- FBA: `Inventories(...).get_inventory_summary_marketplace(...)`.

### 5b. Amazon Ads API — campaigns, bids, create
Ads API is separate from SP-API (different auth + base URL,
`https://advertising-api.amazon.com`, region EU for UAE). Flow:
1. OAuth (LWA) → access token. 2. Pass `Amazon-Advertising-API-ClientId` +
`Amazon-Advertising-API-Scope: <ads_profile_id>` headers.

```python
def get_campaigns(self):
    if self.use_mock:
        return mock_data.ad_campaigns()
    import requests
    token = self._ads_access_token()      # implement OAuth refresh
    headers = {
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": self._credentials()["lwa_client_id"],
        "Amazon-Advertising-API-Scope": self._credentials()["ads_profile_id"],
        "Content-Type": "application/vnd.spCampaign.v3+json",
    }
    r = requests.post("https://advertising-api-eu.amazon.com/sp/campaigns/list",
                      headers=headers, json={})
    # then call the reporting API (v3) for spend/acos/impressions, merge, and
    # return columns: campaign, spend_today, avg_daily, impressions, clicks, acos, sales
```
`create_campaign(payload)` → POST `/sp/campaigns`, then `/sp/adGroups`,
then `/sp/keywords` using `payload["keywords"]`.

### 5c. Inventory website — `core/inventory_source.py`
The stub already does `GET {base}/api/products` with a Bearer token. Just make
your endpoint return JSON rows with columns `sku, title, brand, category,
warehouse_qty, cost` (or adjust the mapping in that function). Turn off
`use_mock_inventory` in Settings.

### 5d. connect.oskarme.com — `core/oskar_source.py`
- **Mode A** `fetch_images_from_media_link(media_link, sku)` → return
  `{"images": [url,...], "ok": bool, "reason": str}`.
- **Mode B** `scrape_product_from_url(url)` → return
  `{"ok", "reason", "title", "price", "description", "specs", "images"}`.
  A generic Open-Graph/JSON-LD scraper is already implemented as the fallback;
  add the oskarme API call above it for supported URLs.

### 5e. Anthropic assistant — already wired
Just paste your key in Settings (`anthropic_api_key`). Model is
`core/assistant.py::MODEL = "claude-opus-4-20250514"`. The live context sent to
Claude is built in `assistant.build_context()` — add fields there to give it
more awareness.

### 5f. Email + Telegram — already wired
`core/notifier.py`. Fill SMTP / Telegram fields in Settings and toggle the
channels on. Use the **Settings → Test** tab to send a test message.

---

## 6. Adding a new page (3 steps)

1. Create `modules/my_page.py`:
   ```python
   import streamlit as st
   from core.components import page_header
   def render(nav=None):
       page_header("My Page", "what it does", icon="🧩")
       st.write("hello")
   ```
2. Import + register in `app.py`:
   ```python
   from modules import my_page
   PAGES = { ... , "My Page": ("🧩", my_page.render) }
   ```
3. Restart. It appears in the sidebar automatically.

Reusable building blocks: `kpi_row`, `styled_table`, `export_buttons`,
`page_header` (in `core/components.py`); `badge`, `alert`, `headline`,
`section_label`, `glow_block` (in `core/styles.py`); tasks via
`db.add_task(...)`.

---

## 7. Change the login password

In `core/auth.py`, the valid credential is a SHA-256 hash of `username|password`.
To set new credentials, compute the hash and replace `_VALID_HASHES`:

```powershell
.\venv\Scripts\Activate.ps1
python -c "import hashlib; print(hashlib.sha256('admin|MyNewPass123'.encode()).hexdigest())"
```
Paste the printed hash:
```python
_VALID_HASHES = {"<the-hash-you-printed>"}
```

---

## 8. Database — schema & backup

Tables (see `core/db.py::init_db`): `settings`, `tasks`, `price_history`,
`catalog`, `stock_rules`, `ready_to_list`, `chat_history`.

- **Back up your data:** copy `data\seller.db` somewhere safe. It holds your
  settings, secrets, tasks and price history.
- **Reset everything:** delete `data\seller.db`; it's recreated empty on next launch.
- Inspect it with any SQLite browser (e.g. "DB Browser for SQLite").

---

## 9. Verify nothing is broken after an edit

```powershell
.\venv\Scripts\Activate.ps1
python -m py_compile app.py core\*.py modules\*.py   # syntax check
streamlit run app.py                                  # run it
```
If a page errors, Streamlit shows the traceback in the browser and terminal —
the file + line number tell you exactly where to look.

---

## 10. Backup checklist (so you never lose this)

- [ ] Keep the whole `seller_dashboard\` folder (the source of truth).
- [ ] Keep `seller_dashboard_full.zip` (portable copy) in a second location / cloud.
- [ ] Keep `ALL_CODE.md` (every file in one document) and this `DEVELOPER_GUIDE.md`.
- [ ] Optionally `git init` the folder and push to a private GitHub repo:
  ```powershell
  cd "C:\Users\Admin\Desktop\New folder\seller_dashboard"
  git init ; git add . ; git commit -m "Initial dashboard"
  ```
  (`.gitignore` already excludes `venv/`, `__pycache__/`, and `*.db`.)
```
