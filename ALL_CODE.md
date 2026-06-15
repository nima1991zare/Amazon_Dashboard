# Amazon.ae Seller Management Dashboard - FULL SOURCE + GUIDE


================================================================
FILE: DEVELOPER_GUIDE.md
================================================================
```markdown
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
```

================================================================
FILE: README.md
================================================================
```markdown
# 🛒 Amazon.ae Seller Management Dashboard (Local-First, API-Ready)

A modular, local-host **Streamlit** control center for running a single Amazon.ae
seller account end-to-end. It runs **today** on mock data + inventory-website
fetch + manual file uploads, and swaps cleanly to **live Amazon SP-API / Ads API**
later by flipping `USE_MOCK` and filling clearly-marked `TODO` stubs in
`core/api_client.py`. All config, tasks, price history and chat are persisted in
**SQLite**.

---

## 🚀 Run it (Windows PowerShell)

```powershell
cd seller_dashboard
python -m venv venv ; .\venv\Scripts\Activate.ps1 ; pip install -r requirements.txt ; streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

### 🔑 Login
| Username | Password |
|---|---|
| `admin` | `your local password` |
(SHA-256 verified, session-state gated.)

---

## 🧩 The 14 modules
1. **🏠 Home — Daily Action Center** — headline KPIs + one prioritized task feed (from the central Tasks table); each task navigates to its section.
2. **📥 Inventory & Listing Intake + Auto Item Creation** — fetch/upload products, classify New Arrival vs Restock, *Mark as listed*; **Auto Item Creation** Mode A (price list + media-link image fetch) / Mode B (URL scrape) → optimize → editable review table → Approve → *Ready to List* queue.
3. **🪄 Listing Optimization** — policy-safe Title/Bullets/Keywords/Description from category best-seller keywords.
4. **📦 Stock Management** — match Amazon + Warehouse files (SKU/ASIN/barcode + fuzzy), apply per-brand/category rules, out-of-stock list; **Stock Configuration** sub-page persists thresholds.
5. **💰 Pricing** — fee calculator (min + target-profit price), Lost Buybox list, Market Tracker (manual/auto) with Noon/UAE price fetch + price-history chart.
6. **📢 Advertising** — campaign KPIs, flashing budget alarm + notify, prebuilt campaign generator, bid/target optimization.
7. **📊 Market Analysis** — you vs market, flag trending+well-priced → A+/ads, lever suggestions (e.g. 10% coupon).
8. **🔥 Deals** — Amazon deal candidates + best deal price per item.
9. **🎨 Asset Management** — A+ content suggestions + video upload status (Uploaded/Not Uploaded).
10. **🚚 FBA / Warehouse Optimization** — upload FBA inventory → resend quantities + stuck-item recommendations.
11. **📅 Event Planner** — Amazon retail calendar; surfaces upcoming events as Home tasks.
12. **🧾 Orders & Profit** — orders table + per-item profit/margin + plotly charts.
13. **⚙️ Settings** — inventory URL/auth, oskar URL/auth, Telegram, SMTP, Anthropic key, Amazon keys, USE_MOCK toggles, notification triggers, **test send**.
14. **🤖 AI Assistant** — full-page chat + sidebar quick-ask, grounded in live DB context; Anthropic-powered (`claude-opus-4-20250514`) with rule-based fallback; write-actions behind confirmation; history in SQLite.

Every list/table page has **CSV + Excel export**. Every action page feeds the
**central Tasks table**. Notifications (email + Telegram) fire on out-of-stock,
lost buybox, over-budget campaigns and high-priority tasks (toggle in Settings).

---

## 🗂️ Project structure

```
seller_dashboard/
  app.py                      # page config, login gate, sidebar nav, router
  requirements.txt
  README.md
  .gitignore
  data/                       # SQLite DB lives here (git-ignored)
  core/
    __init__.py
    db.py                     # SQLite init + ALL read/write helpers
    api_client.py             # ABSTRACTION LAYER for every Amazon call (USE_MOCK + TODO stubs)
    oskar_source.py           # product enrichment: Mode A media images / Mode B URL scrape
    inventory_source.py       # fetch product list from your inventory website
    notifier.py               # send_email() (SMTP) + send_telegram() + notify_event()
    assistant.py              # AI logic: live context + Anthropic call / rule-based fallback
    mock_data.py              # all mock datasets, cached
    styles.py                 # CSS design tokens, glass cards, badges, alerts
    auth.py                   # SHA-256 session-state login
    components.py             # KPI rows, styled tables, CSV+Excel export button
    util.py                   # fuzzy column detection + item matching for messy files
  modules/
    __init__.py
    home.py                   # 1
    intake.py                 # 2  (+ Auto Item Creation)
    optimization.py           # 3
    stock.py                  # 4
    pricing.py                # 5
    advertising.py            # 6
    market_analysis.py        # 7
    deals.py                  # 8
    assets.py                 # 9
    fba.py                    # 10
    events.py                 # 11
    orders_profit.py          # 12
    settings.py               # 13
    ai_assistant.py           # 14
```

---

## 🔧 How to make changes (where common edits go)

| I want to… | Edit |
|---|---|
| Wire a real Amazon API call | `core/api_client.py` — find the method, flip `USE_MOCK`/Settings toggle, fill the `TODO`. |
| Change/seed mock data | `core/mock_data.py` |
| Connect my inventory website | Settings → URL+token, then `core/inventory_source.py::fetch_inventory()` TODO. |
| Wire connect.oskarme.com | Settings → URL+token, then `core/oskar_source.py` TODOs (Mode A/B). |
| Adjust column auto-detection for my files | `core/util.py` → `_FIELD_ALIASES`. |
| Change the DB schema or add a table/helper | `core/db.py` (single source of truth). |
| Restyle the UI | `core/styles.py` (tokens + CSS). |
| Add/rename a page | add a `modules/<name>.py` with `render(nav)`, register it in `app.py::PAGES`. |
| Tune notification triggers | Settings → Notifications, logic in `core/notifier.py`. |
| Switch the AI model | `core/assistant.py::MODEL`. |

### Mock → live checklist
1. Settings → turn off the relevant **Use MOCK** toggle.
2. Fill credentials in Settings (stored in SQLite).
3. Implement the matching `TODO` in `api_client.py` / `inventory_source.py` / `oskar_source.py`.
4. The UI is unchanged — it only ever calls the abstraction layer.

---

## 🔒 Notes
- Secrets are stored in the local SQLite DB (`data/seller.db`), which is git-ignored.
- The AI assistant only **suggests**; all write-actions (tasks, listings, prices) require an explicit confirmation click.
- Built and tested on Python 3.11+.
```
```

================================================================
FILE: app.py
================================================================
```python
"""
app.py — Amazon.ae Seller Management Dashboard
==============================================
Entry point: page config → DB init → login gate → sidebar nav → router.

Run (Windows PowerShell):
    python -m venv venv ; .\\venv\\Scripts\\Activate.ps1 ; pip install -r requirements.txt ; streamlit run app.py

Architecture: see README.md "Project structure". Every Amazon call goes through
core/api_client.py; every durable thing lives in core/db.py (SQLite). Pages live
in modules/ and expose a render(nav) function.
"""

from __future__ import annotations
import os
from datetime import datetime
import streamlit as st

st.set_page_config(page_title="Amazon.ae Seller Command", page_icon="🛒",
                   layout="wide", initial_sidebar_state="expanded")

# Version shown in the sidebar + launcher terminal so you can confirm the build.
APP_VERSION = "1.5"


def _build_stamp() -> str:
    """Last-updated timestamp from the running file's own modification time."""
    try:
        ts = os.path.getmtime(os.path.abspath(__file__))
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""

from core import db
from core.auth import login_gate, logout
from core.styles import inject_global_css
from core import mock_data

from modules import (home, intake, optimization, stock, pricing, advertising,
                     market_analysis, deals, assets, aplus_studio, fba,
                     hazmat_inactive, events, orders_profit,
                     settings as settings_mod, ai_assistant)

# Page registry: label → (icon, render fn). Order = sidebar order.
PAGES = {
    "Home":                              ("🏠", home.render),
    "Inventory & Listing Intake":        ("📥", intake.render),
    "Listing Optimization":              ("🪄", optimization.render),
    "Stock Management":                  ("📦", stock.render),
    "Pricing":                           ("💰", pricing.render),
    "Advertising":                       ("📢", advertising.render),
    "Market Analysis":                   ("📊", market_analysis.render),
    "Deals":                             ("🔥", deals.render),
    "Asset Management":                  ("🎨", assets.render),
    "A+ Content Studio":                 ("✨", aplus_studio.render),
    "FBA / Warehouse Optimization":      ("🚚", fba.render),
    "Hazmat & Inactive":                 ("☣️", hazmat_inactive.render),
    "Event Planner":                     ("📅", events.render),
    "Orders & Profit":                   ("🧾", orders_profit.render),
    "AI Assistant":                      ("🤖", ai_assistant.render),
    "Settings":                          ("⚙️", settings_mod.render),
}


def _bootstrap() -> None:
    """One-time DB init + catalog seed so classification has a baseline."""
    if st.session_state.get("_booted"):
        return
    db.init_db()
    db.seed_catalog_if_empty(mock_data.catalog_seed())
    st.session_state["_booted"] = True


def _navigate(page_label: str) -> None:
    """Programmatic navigation used by Home task 'Go' buttons."""
    if page_label in PAGES:
        st.session_state["nav_choice"] = page_label
        st.rerun()


def _sidebar() -> str:
    with st.sidebar:
        st.markdown(
            "<div style='text-align:center; padding:6px 0 2px'>"
            "<div style='font-size:2rem'>🛒</div>"
            "<div style='font-weight:800; font-size:1.1rem'>Seller Command</div>"
            "<div style='color:var(--muted); font-size:.72rem'>Amazon.ae · Local-First</div></div>",
            unsafe_allow_html=True)
        st.markdown("---")
        st.markdown(
            f"<div style='font-size:.8rem; color:var(--muted)'>Signed in as</div>"
            f"<div style='font-weight:700; margin-bottom:6px'>👤 {st.session_state.get('username','admin')}</div>",
            unsafe_allow_html=True)

        labels = list(PAGES.keys())
        # Honor programmatic navigation requests.
        default_idx = labels.index(st.session_state.get("nav_choice", "Home")) \
            if st.session_state.get("nav_choice") in labels else 0
        if st.session_state.pop("goto_assistant", False):
            default_idx = labels.index("AI Assistant")

        choice = st.radio("Navigation", labels, index=default_idx,
                          format_func=lambda k: f"{PAGES[k][0]}  {k}",
                          label_visibility="collapsed", key="nav_radio")
        st.session_state["nav_choice"] = choice

        # Persistent AI quick-ask.
        ai_assistant.render_sidebar_quickask()

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🚪 Logout", use_container_width=True):
                logout()
        with c2:
            open_n = db.count_open_tasks()
            st.markdown(f"<div style='text-align:center; padding-top:6px'>"
                        f"<span class='badge badge-coral'>{open_n} tasks</span></div>",
                        unsafe_allow_html=True)
        st.markdown(
            f"<div style='text-align:center; color:var(--muted); font-size:.7rem; margin-top:10px'>"
            f"v{APP_VERSION} · updated {_build_stamp()}</div>",
            unsafe_allow_html=True)
    return choice


def main() -> None:
    if not login_gate():
        return
    inject_global_css()
    _bootstrap()
    selected = _sidebar()
    _, render_fn = PAGES[selected]
    render_fn(_navigate)  # all modules accept nav (most ignore it)


if __name__ == "__main__":
    main()
```

================================================================
FILE: requirements.txt
================================================================
```text
streamlit>=1.36
pandas>=2.0
plotly>=5.20
requests>=2.31
beautifulsoup4>=4.12
openpyxl>=3.1
pypdf>=4.0
anthropic>=0.39
openai>=1.40
```

================================================================
FILE: .gitignore
================================================================
```text
# Python
__pycache__/
*.py[cod]
*.egg-info/
.ipynb_checkpoints/

# Virtual environments
venv/
.venv/
env/

# Local database & data
data/*.db
*.sqlite
*.sqlite3

# Secrets / local config (settings are stored in the DB, but ignore any stray files)
secrets/
*.secret
.env
config.local.*

# Streamlit
.streamlit/secrets.toml

# OS / editor
.DS_Store
Thumbs.db
.vscode/
.idea/
```

================================================================
FILE: core/__init__.py
================================================================
```python
"""Core package: persistence, abstractions, connectors, styling and assistant."""
```

================================================================
FILE: core/db.py
================================================================
```python
"""
core/db.py
==========
SQLite persistence layer. EVERYTHING durable lives here: user settings/secrets,
the central Tasks feed, captured price history, the known Amazon catalog (used to
classify new-arrival vs restock), per-brand/category stock rules, a "ready to
list" queue, and the AI assistant chat history.

All other modules import these helpers — they never touch sqlite3 directly. This
keeps the storage concern in one file so the schema can evolve in one place.

The DB file path defaults to  data/seller.db  next to the project.
"""

from __future__ import annotations
import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

# Resolve <project>/data/seller.db regardless of where the app is launched from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
DB_PATH = os.path.join(_PROJECT_ROOT, "data", "seller.db")


def _now() -> str:
    """UTC ISO timestamp string (stable, sortable)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _conn():
    """Context-managed connection with row factory + foreign keys on."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every launch."""
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT,
                title       TEXT NOT NULL,
                detail      TEXT,
                module      TEXT,          -- which page this task routes to
                priority    TEXT,          -- high | medium | low
                status      TEXT,          -- open | done
                related_id  TEXT           -- optional SKU/ASIN/campaign id
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                captured_at TEXT,
                item_id     TEXT,
                item_name   TEXT,
                source      TEXT,          -- amazon | noon | other | mine
                price       REAL
            );

            CREATE TABLE IF NOT EXISTS catalog (
                sku        TEXT PRIMARY KEY,
                asin       TEXT,
                title      TEXT,
                brand      TEXT,
                category   TEXT,
                status     TEXT,           -- listed | pending
                last_seen  TEXT
            );

            CREATE TABLE IF NOT EXISTS stock_rules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_type  TEXT,          -- brand | category
                scope_value TEXT,
                min_stock   INTEGER,
                UNIQUE(scope_type, scope_value)
            );

            CREATE TABLE IF NOT EXISTS ready_to_list (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT,
                sku         TEXT,
                title       TEXT,
                price       REAL,
                images      TEXT,          -- JSON list of urls
                payload     TEXT           -- JSON of full optimized listing
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT,
                role        TEXT,          -- user | assistant
                content     TEXT
            );

            CREATE TABLE IF NOT EXISTS fulfilment_overrides (
                sku        TEXT PRIMARY KEY,
                channel    TEXT,           -- FBA | FBM
                updated_at TEXT
            );
            """
        )


# ---------------------------------------------------------------------------
# SETTINGS / SECRETS
# ---------------------------------------------------------------------------
def set_setting(key: str, value) -> None:
    """Upsert a single setting. Non-str values are JSON-encoded."""
    if not isinstance(value, str):
        value = json.dumps(value)
    with _conn() as c:
        c.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_setting(key: str, default: str = "") -> str:
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def get_all_settings() -> dict:
    with _conn() as c:
        rows = c.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


# ---------------------------------------------------------------------------
# TASKS  (the central action feed shown on Home)
# ---------------------------------------------------------------------------
def add_task(title: str, detail: str = "", module: str = "", priority: str = "medium",
             related_id: str = "", dedupe: bool = True) -> None:
    """Insert a task. If dedupe, skip when an identical open task already exists."""
    with _conn() as c:
        if dedupe:
            existing = c.execute(
                "SELECT id FROM tasks WHERE title=? AND status='open'", (title,)
            ).fetchone()
            if existing:
                return
        c.execute(
            "INSERT INTO tasks(created_at,title,detail,module,priority,status,related_id) "
            "VALUES(?,?,?,?,?, 'open', ?)",
            (_now(), title, detail, module, priority, related_id),
        )


def get_tasks(status: str | None = "open") -> list[dict]:
    """Return tasks ordered by priority (high→low) then recency."""
    order = "CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, created_at DESC"
    with _conn() as c:
        if status:
            rows = c.execute(
                f"SELECT * FROM tasks WHERE status=? ORDER BY {order}", (status,)
            ).fetchall()
        else:
            rows = c.execute(f"SELECT * FROM tasks ORDER BY {order}").fetchall()
    return [dict(r) for r in rows]


def complete_task(task_id: int) -> None:
    with _conn() as c:
        c.execute("UPDATE tasks SET status='done' WHERE id=?", (task_id,))


def clear_tasks() -> None:
    with _conn() as c:
        c.execute("DELETE FROM tasks")


def count_open_tasks() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) n FROM tasks WHERE status='open'").fetchone()["n"]


# ---------------------------------------------------------------------------
# PRICE HISTORY  (market tracker)
# ---------------------------------------------------------------------------
def add_price(item_id: str, item_name: str, source: str, price: float) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO price_history(captured_at,item_id,item_name,source,price) "
            "VALUES(?,?,?,?,?)",
            (_now(), item_id, item_name, source, float(price)),
        )


def get_price_history(item_id: str | None = None) -> list[dict]:
    with _conn() as c:
        if item_id:
            rows = c.execute(
                "SELECT * FROM price_history WHERE item_id=? ORDER BY captured_at", (item_id,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM price_history ORDER BY captured_at").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# CATALOG  (decides NEW ARRIVAL vs RESTOCK)
# ---------------------------------------------------------------------------
def upsert_catalog_item(sku: str, asin: str = "", title: str = "", brand: str = "",
                        category: str = "", status: str = "listed") -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO catalog(sku,asin,title,brand,category,status,last_seen) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(sku) DO UPDATE SET "
            "asin=excluded.asin, title=excluded.title, brand=excluded.brand, "
            "category=excluded.category, status=excluded.status, last_seen=excluded.last_seen",
            (sku, asin, title, brand, category, status, _now()),
        )


def get_catalog_skus() -> set[str]:
    with _conn() as c:
        rows = c.execute("SELECT sku FROM catalog").fetchall()
    return {r["sku"] for r in rows}


def get_catalog() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM catalog").fetchall()
    return [dict(r) for r in rows]


def seed_catalog_if_empty(items: list[dict]) -> None:
    """Populate the catalog with a baseline set on first run so the new-arrival
    vs restock classification has something to compare against."""
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) n FROM catalog").fetchone()["n"]
    if n == 0:
        for it in items:
            upsert_catalog_item(
                sku=it.get("sku", ""), asin=it.get("asin", ""),
                title=it.get("title", ""), brand=it.get("brand", ""),
                category=it.get("category", ""), status="listed",
            )


# ---------------------------------------------------------------------------
# STOCK RULES
# ---------------------------------------------------------------------------
def set_stock_rule(scope_type: str, scope_value: str, min_stock: int) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO stock_rules(scope_type,scope_value,min_stock) VALUES(?,?,?) "
            "ON CONFLICT(scope_type,scope_value) DO UPDATE SET min_stock=excluded.min_stock",
            (scope_type, scope_value, int(min_stock)),
        )


def get_stock_rules() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM stock_rules ORDER BY scope_type, scope_value").fetchall()
    return [dict(r) for r in rows]


def stock_threshold_for(brand: str = "", category: str = "", default: int = 10) -> int:
    """Resolve the min-stock threshold for an item: brand rule wins over category
    rule, which wins over the global default."""
    rules = {(r["scope_type"], r["scope_value"]): r["min_stock"] for r in get_stock_rules()}
    if ("brand", brand) in rules:
        return rules[("brand", brand)]
    if ("category", category) in rules:
        return rules[("category", category)]
    return default


# ---------------------------------------------------------------------------
# FULFILMENT CHANNEL OVERRIDES  (set from Hazmat; read by Stock/Inventory views)
# ---------------------------------------------------------------------------
def set_channel_override(sku: str, channel: str) -> None:
    """Persist an FBA/FBM channel decision so every view reflects it."""
    with _conn() as c:
        c.execute(
            "INSERT INTO fulfilment_overrides(sku,channel,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(sku) DO UPDATE SET channel=excluded.channel, updated_at=excluded.updated_at",
            (sku, channel, _now()),
        )


def get_channel_overrides() -> dict:
    with _conn() as c:
        rows = c.execute("SELECT sku, channel FROM fulfilment_overrides").fetchall()
    return {r["sku"]: r["channel"] for r in rows}


def get_channel_override(sku: str, default: str = "") -> str:
    return get_channel_overrides().get(sku, default)


# ---------------------------------------------------------------------------
# READY TO LIST  (Auto Item Creation approval queue)
# ---------------------------------------------------------------------------
def add_ready_to_list(sku: str, title: str, price: float, images: list, payload: dict) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO ready_to_list(created_at,sku,title,price,images,payload) "
            "VALUES(?,?,?,?,?,?)",
            (_now(), sku, title, float(price or 0), json.dumps(images), json.dumps(payload)),
        )


def get_ready_to_list() -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM ready_to_list ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["images"] = json.loads(d["images"]) if d["images"] else []
        d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# CHAT HISTORY
# ---------------------------------------------------------------------------
def add_chat(role: str, content: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO chat_history(created_at,role,content) VALUES(?,?,?)",
            (_now(), role, content),
        )


def get_chat(limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_chat() -> None:
    with _conn() as c:
        c.execute("DELETE FROM chat_history")
```

================================================================
FILE: core/api_client.py
================================================================
```python
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
        types = sp_api.search_product_types(keywords)
        return types or mock_data.PRODUCT_TYPES

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
```

================================================================
FILE: core/sp_api.py
================================================================
```python
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
    resp = requests.post(LWA_TOKEN_URL, data={
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
    r = requests.get(f"{c['endpoint']}/definitions/2020-09-01/productTypes",
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
        if enum:
            ftype, options = "select", list(enum)
        elif leaf.get("type") in ("number", "integer"):
            ftype = "number"
        elif leaf.get("maxLength", 0) and leaf["maxLength"] > 120:
            ftype = "textarea"
        fields.append({"name": name, "label": p.get("title", name).strip() or name,
                       "required": name in required, "type": ftype, "options": options,
                       "max": leaf.get("maxLength")})
    return fields


def get_requirements(product_type: str) -> list[dict]:
    import requests
    c = creds()
    r = requests.get(f"{c['endpoint']}/definitions/2020-09-01/productTypes/{product_type}",
                     params={"marketplaceIds": c["marketplace_id"], "requirements": "LISTING",
                             "locale": "DEFAULT", "sellerId": c["seller_id"]},
                     headers=_headers(), timeout=25)
    r.raise_for_status()
    meta = r.json()
    schema_url = meta["schema"]["link"]["resource"]
    sch = requests.get(schema_url, timeout=25).json()   # pre-signed URL, no auth
    return _parse_schema(sch)


# ---------------------------------------------------------------------------
# Catalog Items 2022-04-01 — does the product already exist?
# ---------------------------------------------------------------------------
def search_catalog_items(identifier: str, id_type: str = "GTIN") -> list[dict]:
    import requests
    c = creds()
    r = requests.get(f"{c['endpoint']}/catalog/2022-04-01/items",
                     params={"marketplaceIds": c["marketplace_id"],
                             "identifiers": str(identifier), "identifiersType": id_type,
                             "includedData": "identifiers,summaries,productTypes"},
                     headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json().get("items", [])


# ---------------------------------------------------------------------------
# Attribute mapping (flat form values -> SP-API nested attributes)
# ---------------------------------------------------------------------------
def to_sp_attributes(flat: dict, mp: str) -> dict:
    special = {"standard_price", "list_price", "quantity", "fulfillment_channel",
               "main_image_url", "external_product_id", "external_product_id_type",
               "condition_type", "parentage_level", "variation_theme",
               "child_relationship_type", "color_name", "country_of_origin",
               "shipping_weight", "shipping_weight_unit",
               "item_length", "item_width", "item_height", "dimension_unit",
               "package_weight", "package_weight_unit",
               "package_length", "package_width", "package_height", "package_dimension_unit",
               "battery_cell_composition", "battery_type", "number_of_batteries",
               "battery_weight", "battery_weight_unit", "lithium_energy",
               "lithium_energy_unit", "lithium_packaging", "lithium_weight",
               "lithium_weight_unit"}
    is_parent = flat.get("parentage_level") == "parent"
    out: dict = {}
    for k, v in flat.items():
        # Skip blanks and zero-valued optional numbers (e.g. don't send
        # max_order_quantity=0, which Amazon rejects as < 1).
        if k in special or v in (None, "") or v == 0:
            continue
        if isinstance(v, str) and "\n" in v:
            out[k] = [{"value": ln.strip(), "marketplace_id": mp}
                      for ln in v.splitlines() if ln.strip()]
        else:
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
    if flat.get("child_relationship_type"):
        out["child_relationship_type"] = [{"value": flat["child_relationship_type"],
                                           "marketplace_id": mp}]
    if flat.get("color_name"):
        out["color_name"] = [{"value": flat["color_name"], "marketplace_id": mp}]

    # --- offer attributes (skip entirely for a parent — it has no buyable offer) ---
    if not is_parent:
        if flat.get("standard_price"):
            # UAE marketplace expects a tax-inclusive list price (value_with_tax).
            out["list_price"] = [{"currency": "AED",
                                  "value_with_tax": float(flat["standard_price"]),
                                  "marketplace_id": mp}]
        if flat.get("external_product_id"):
            out["externally_assigned_product_identifier"] = [{
                "value": str(flat["external_product_id"]),
                "type": (flat.get("external_product_id_type") or "ean").lower(),
                "marketplace_id": mp}]
        channel = flat.get("fulfillment_channel", "FBM")
        if channel == "FBA":
            out["fulfillment_availability"] = [{"fulfillment_channel_code": "AMAZON_EU"}]
        else:
            out["fulfillment_availability"] = [{"fulfillment_channel_code": "DEFAULT",
                                                "quantity": int(float(flat.get("quantity", 1) or 1))}]
    if flat.get("main_image_url"):
        out["main_product_image_locator"] = [{"media_location": flat["main_image_url"],
                                              "marketplace_id": mp}]
    # Shipping weight (value + unit).
    if flat.get("shipping_weight"):
        out["website_shipping_weight"] = [{"value": float(flat["shipping_weight"]),
                                           "unit": flat.get("shipping_weight_unit", "kilograms"),
                                           "marketplace_id": mp}]
    # Item dimensions (depth/width/height + unit).
    if flat.get("item_length") and flat.get("item_width") and flat.get("item_height"):
        u = flat.get("dimension_unit", "centimeters")
        out["item_depth_width_height"] = [{
            "depth": {"value": float(flat["item_length"]), "unit": u},
            "width": {"value": float(flat["item_width"]), "unit": u},
            "height": {"value": float(flat["item_height"]), "unit": u},
            "marketplace_id": mp}]
    # Package weight (value + unit).
    if flat.get("package_weight"):
        out["item_package_weight"] = [{"value": float(flat["package_weight"]),
                                       "unit": flat.get("package_weight_unit", "kilograms"),
                                       "marketplace_id": mp}]
    # Package dimensions (length/width/height + unit).
    if flat.get("package_length") and flat.get("package_width") and flat.get("package_height"):
        u = flat.get("package_dimension_unit", "centimeters")
        out["item_package_dimensions"] = [{
            "length": {"value": float(flat["package_length"]), "unit": u},
            "width": {"value": float(flat["package_width"]), "unit": u},
            "height": {"value": float(flat["package_height"]), "unit": u},
            "marketplace_id": mp}]
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
            "attributes": to_sp_attributes(flat_attributes, c["marketplace_id"])}
    url = (f"{c['endpoint']}/listings/2021-08-01/items/{c['seller_id']}/"
           f"{requests.utils.quote(str(sku), safe='')}")
    r = requests.put(url, params={"marketplaceIds": c["marketplace_id"],
                                  "issueLocale": c["issue_locale"], "mode": "VALIDATION_PREVIEW"},
                     headers=_headers(), json=body, timeout=30)
    try:
        j = r.json()
    except Exception:
        j = {"raw": r.text[:400]}
    issues = j.get("issues", [])
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
        messages.append({
            "messageId": i, "sku": it["sku"], "operationType": "UPDATE",
            "productType": it.get("product_type", "PRODUCT"),
            "requirements": it.get("requirements", "LISTING"),
            "attributes": to_sp_attributes(it.get("attributes", {}), mp),
        })
    return {"header": {"sellerId": c["seller_id"], "version": "2.0",
                       "issueLocale": c["issue_locale"]},
            "messages": messages}


def _create_feed_document() -> dict:
    import requests
    c = creds()
    r = requests.post(f"{c['endpoint']}/feeds/2021-06-30/documents",
                      headers=_headers(), json={"contentType": "application/json; charset=UTF-8"},
                      timeout=20)
    r.raise_for_status()
    return r.json()  # {feedDocumentId, url}


def _upload_feed(url: str, content: bytes) -> None:
    import requests
    up = requests.put(url, data=content,
                      headers={"Content-Type": "application/json; charset=UTF-8"}, timeout=40)
    up.raise_for_status()


def _create_feed(feed_document_id: str) -> str:
    import requests
    c = creds()
    r = requests.post(f"{c['endpoint']}/feeds/2021-06-30/feeds", headers=_headers(),
                      json={"feedType": "JSON_LISTINGS_FEED",
                            "marketplaceIds": [c["marketplace_id"]],
                            "inputFeedDocumentId": feed_document_id}, timeout=20)
    r.raise_for_status()
    return r.json()["feedId"]


def _get_feed(feed_id: str) -> dict:
    import requests
    c = creds()
    r = requests.get(f"{c['endpoint']}/feeds/2021-06-30/feeds/{feed_id}",
                     headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def _get_feed_document(doc_id: str) -> dict:
    import requests
    c = creds()
    r = requests.get(f"{c['endpoint']}/feeds/2021-06-30/documents/{doc_id}",
                     headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()


def submit_listings_feed(items: list[dict], poll_timeout: int = 90) -> dict:
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
        rep = requests.get(d["url"], timeout=30)
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
        r = requests.get(c["endpoint"] + "/orders/v0/orders", params=params,
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
    r = requests.get(c["endpoint"] + "/fba/inventory/v1/summaries",
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
```

================================================================
FILE: core/oskar_source.py
================================================================
```python
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
```

================================================================
FILE: core/inventory_source.py
================================================================
```python
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
```

================================================================
FILE: core/notifier.py
================================================================
```python
"""
core/notifier.py
================
Outbound notifications: email (SMTP) and Telegram (bot API). Credentials and
channel toggles are read from Settings (DB) — nothing hard-coded.

notify_event() is the high-level entry the modules call; it checks whether the
event type is enabled in Settings before sending, and fans out to whichever
channels are configured. Every send returns (ok, message) and never raises into
the UI.
"""

from __future__ import annotations
import smtplib
from email.mime.text import MIMEText

from core import db


# ---------------------------------------------------------------------------
# Low-level channels
# ---------------------------------------------------------------------------
def send_email(subject: str, body: str, to_addr: str | None = None) -> tuple[bool, str]:
    host = db.get_setting("smtp_host", "")
    port = int(db.get_setting("smtp_port", "587") or 587)
    user = db.get_setting("smtp_user", "")
    password = db.get_setting("smtp_password", "")
    sender = db.get_setting("smtp_from", user)
    to_addr = to_addr or db.get_setting("smtp_to", user)

    if not (host and user and password and to_addr):
        return False, "SMTP not fully configured in Settings"

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_addr
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(sender, [to_addr], msg.as_string())
        return True, f"email sent to {to_addr}"
    except Exception as e:
        return False, f"email error: {e}"


def send_telegram(text: str) -> tuple[bool, str]:
    token = db.get_setting("telegram_bot_token", "")
    chat_id = db.get_setting("telegram_chat_id", "")
    if not (token and chat_id):
        return False, "Telegram not configured in Settings"
    try:
        import requests
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url, json={"chat_id": chat_id, "text": text,
                                        "parse_mode": "HTML"}, timeout=12)
        if resp.status_code == 200:
            return True, "telegram sent"
        return False, f"telegram http {resp.status_code}: {resp.text[:120]}"
    except Exception as e:
        return False, f"telegram error: {e}"


# ---------------------------------------------------------------------------
# High-level event dispatch
# ---------------------------------------------------------------------------
# Settings keys that toggle each trigger type.
EVENT_TOGGLE_KEYS = {
    "out_of_stock":   "notify_on_out_of_stock",
    "lost_buybox":    "notify_on_lost_buybox",
    "budget":         "notify_on_budget",
    "daily_tasks":    "notify_on_daily_tasks",
}


def event_enabled(event_type: str) -> bool:
    key = EVENT_TOGGLE_KEYS.get(event_type)
    return db.get_setting(key, "1") == "1" if key else True


def notify_event(event_type: str, subject: str, body: str) -> list[tuple[str, bool, str]]:
    """Dispatch a business event to all enabled channels.

    Returns a list of (channel, ok, message) for display/logging.
    """
    results = []
    if not event_enabled(event_type):
        return [("(disabled)", False, f"'{event_type}' notifications are off in Settings")]

    if db.get_setting("channel_email", "0") == "1":
        ok, msg = send_email(subject, body)
        results.append(("email", ok, msg))
    if db.get_setting("channel_telegram", "0") == "1":
        ok, msg = send_telegram(f"<b>{subject}</b>\n{body}")
        results.append(("telegram", ok, msg))

    if not results:
        results.append(("(none)", False, "no channels enabled in Settings"))
    return results
```

================================================================
FILE: core/mock_data.py
================================================================
```python
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
```

================================================================
FILE: core/styles.py
================================================================
```python
"""
core/styles.py
==============
Design tokens + premium dark glassmorphism CSS, plus small HTML helpers for KPI
cards, badges and alert banners. Injected once per page via inject_global_css().

Palette: deep slate backgrounds, neon accents — emerald (ok), amber (warn),
coral (alert), electric blue (actions/AI).
"""

import streamlit as st

PALETTE = {
    "bg_deep": "#0b0f1a", "bg_panel": "#121826",
    "glass": "rgba(255,255,255,0.04)", "glass_border": "rgba(255,255,255,0.08)",
    "text": "#e8edf6", "muted": "#8b97ad",
    "emerald": "#10e0a0", "blue": "#3da9fc", "coral": "#ff5d6c",
    "amber": "#ffb454", "violet": "#a78bfa",
}


def inject_global_css() -> None:
    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    :root {{
        --bg-deep:{PALETTE['bg_deep']}; --glass:{PALETTE['glass']};
        --glass-border:{PALETTE['glass_border']}; --text:{PALETTE['text']};
        --muted:{PALETTE['muted']}; --emerald:{PALETTE['emerald']};
        --blue:{PALETTE['blue']}; --coral:{PALETTE['coral']};
        --amber:{PALETTE['amber']}; --violet:{PALETTE['violet']};
    }}
    .stApp {{
        background:
          radial-gradient(1200px 700px at 15% -10%, rgba(61,169,252,0.10), transparent 55%),
          radial-gradient(1000px 600px at 95% 0%, rgba(167,139,250,0.10), transparent 50%),
          var(--bg-deep);
        color: var(--text); font-family:'Inter',sans-serif;
    }}
    .block-container {{ padding-top:2.0rem; padding-bottom:3rem; max-width:1320px; }}
    h1,h2,h3,h4 {{ color:var(--text); letter-spacing:-0.02em; }}
    h1 {{ font-weight:800; }}
    #MainMenu, footer {{ visibility:hidden; }}
    /* Keep the header present (transparent) so the sidebar expand arrow still works. */
    header[data-testid="stHeader"] {{ background:transparent; }}
    /* Force the collapsed-sidebar expand control to always be visible & clickable. */
    [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{
        visibility:visible !important; opacity:1 !important; display:flex !important;
        z-index:999999 !important; }}
    [data-testid="stSidebarCollapsedControl"] svg, [data-testid="collapsedControl"] svg {{
        color:var(--text) !important; fill:var(--text) !important; }}

    section[data-testid="stSidebar"] {{
        background:linear-gradient(180deg,#0e1422,#0b0f1a);
        border-right:1px solid var(--glass-border);
    }}
    section[data-testid="stSidebar"] * {{ color:var(--text); }}

    .glass-card {{
        background:var(--glass); border:1px solid var(--glass-border);
        border-radius:16px; padding:20px 22px; backdrop-filter:blur(14px);
        box-shadow:0 8px 30px rgba(0,0,0,0.35); transition:transform .18s ease;
    }}
    .glass-card:hover {{ transform:translateY(-3px); border-color:rgba(255,255,255,0.18); }}

    .kpi {{ background:var(--glass); border:1px solid var(--glass-border);
        border-radius:16px; padding:18px 20px; backdrop-filter:blur(14px);
        box-shadow:0 8px 26px rgba(0,0,0,0.30); position:relative; overflow:hidden; }}
    .kpi::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:4px;
        background:var(--accent,var(--blue)); box-shadow:0 0 18px 1px var(--accent,var(--blue)); }}
    .kpi .kpi-label {{ font-size:.78rem; color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-weight:600; }}
    .kpi .kpi-value {{ font-size:2.0rem; font-weight:800; margin:6px 0 2px; line-height:1.05; }}
    .kpi .kpi-sub {{ font-size:.78rem; color:var(--muted); }}

    .glow-block {{ text-align:center; border-radius:18px; padding:26px;
        background:radial-gradient(120% 120% at 50% 0%, rgba(16,224,160,0.18), rgba(16,224,160,0.02));
        border:1px solid rgba(16,224,160,0.35);
        box-shadow:0 0 40px rgba(16,224,160,0.18), inset 0 0 24px rgba(16,224,160,0.06); }}
    .glow-block .gb-value {{ font-size:3rem; font-weight:800; color:var(--emerald); text-shadow:0 0 22px rgba(16,224,160,0.55); }}
    .glow-block .gb-label {{ color:var(--muted); text-transform:uppercase; letter-spacing:.1em; font-size:.8rem; font-weight:600; }}

    .badge {{ display:inline-block; padding:3px 11px; border-radius:999px; font-size:.74rem; font-weight:700; }}
    .badge-green  {{ background:rgba(16,224,160,0.14); color:var(--emerald); border:1px solid rgba(16,224,160,0.4); }}
    .badge-blue   {{ background:rgba(61,169,252,0.14); color:var(--blue);    border:1px solid rgba(61,169,252,0.4); }}
    .badge-amber  {{ background:rgba(255,180,84,0.14); color:var(--amber);   border:1px solid rgba(255,180,84,0.4); }}
    .badge-coral  {{ background:rgba(255,93,108,0.14); color:var(--coral);   border:1px solid rgba(255,93,108,0.4); }}
    .badge-violet {{ background:rgba(167,139,250,0.14);color:var(--violet);  border:1px solid rgba(167,139,250,0.4); }}

    .alert {{ border-radius:14px; padding:14px 18px; margin:6px 0; font-weight:600;
        display:flex; align-items:center; gap:12px; border:1px solid; }}
    .alert-coral {{ background:rgba(255,93,108,0.10); border-color:rgba(255,93,108,0.45); color:#ffd2d7; }}
    .alert-amber {{ background:rgba(255,180,84,0.10); border-color:rgba(255,180,84,0.45); color:#ffe7c4; }}
    .alert-green {{ background:rgba(16,224,160,0.10); border-color:rgba(16,224,160,0.45); color:#c4ffec; }}
    .alert-blue  {{ background:rgba(61,169,252,0.10); border-color:rgba(61,169,252,0.45); color:#cfe7ff; }}
    @keyframes pulseRed {{ 0%{{box-shadow:0 0 0 0 rgba(255,93,108,0.45);}} 70%{{box-shadow:0 0 0 14px rgba(255,93,108,0);}} 100%{{box-shadow:0 0 0 0 rgba(255,93,108,0);}} }}
    .alert-flash {{ animation:pulseRed 1.8s infinite; }}

    .headline {{ display:flex; align-items:center; gap:14px; background:var(--glass);
        border:1px solid var(--glass-border); border-left:4px solid var(--accent,var(--blue));
        border-radius:12px; padding:13px 16px; margin-bottom:10px; }}
    .headline .h-title {{ font-weight:700; font-size:.95rem; }}
    .headline .h-sub {{ color:var(--muted); font-size:.82rem; }}

    .stButton > button {{ background:linear-gradient(135deg,var(--blue),#2b6fd6); color:#fff;
        border:none; border-radius:11px; padding:.5rem 1.1rem; font-weight:700;
        box-shadow:0 6px 18px rgba(61,169,252,0.35); transition:transform .15s ease; }}
    .stButton > button:hover {{ transform:translateY(-2px); box-shadow:0 10px 26px rgba(61,169,252,0.5); }}
    .stDownloadButton > button {{ background:linear-gradient(135deg,var(--emerald),#07b07e);
        color:#04221a; border:none; border-radius:11px; font-weight:700; }}

    .stTextInput input, .stNumberInput input, .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"] {{
        background:rgba(255,255,255,0.03)!important; border:1px solid var(--glass-border)!important;
        border-radius:10px!important; color:var(--text)!important; }}

    .pretty-table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:.85rem;
        border-radius:12px; overflow:hidden; }}
    .pretty-table thead th {{ background:rgba(255,255,255,0.05); color:var(--muted);
        text-transform:uppercase; font-size:.70rem; letter-spacing:.06em; text-align:left;
        padding:11px 14px; font-weight:700; border-bottom:1px solid var(--glass-border); }}
    .pretty-table tbody td {{ padding:10px 14px; border-bottom:1px solid rgba(255,255,255,0.04); }}
    .pretty-table tbody tr:nth-child(even) {{ background:rgba(255,255,255,0.018); }}
    .pretty-table tbody tr:hover {{ background:rgba(61,169,252,0.06); }}
    .row-danger {{ background:rgba(255,93,108,0.09)!important; }}
    .row-warn   {{ background:rgba(255,180,84,0.08)!important; }}
    .row-good   {{ background:rgba(16,224,160,0.07)!important; }}

    .stTabs [data-baseweb="tab"] {{ background:var(--glass); border:1px solid var(--glass-border);
        border-radius:10px 10px 0 0; padding:8px 16px; color:var(--muted); }}
    .stTabs [aria-selected="true"] {{ background:rgba(61,169,252,0.14); color:var(--blue); border-color:rgba(61,169,252,0.4); }}

    .section-label {{ font-size:.76rem; text-transform:uppercase; letter-spacing:.12em;
        color:var(--muted); font-weight:700; margin:4px 0 10px; }}

    .login-hero {{ text-align:center; margin-bottom:8px; }}
    .login-hero .lh-logo {{ font-size:2.6rem; }}
    .login-hero .lh-title {{ font-size:1.7rem; font-weight:800; margin-top:6px; }}
    .login-hero .lh-sub {{ color:var(--muted); font-size:.9rem; }}
    </style>
    """, unsafe_allow_html=True)


# --------------------------- HTML helpers ----------------------------------
def kpi_card(label, value, sub="", accent="blue") -> str:
    hexc = PALETTE.get(accent, PALETTE["blue"])
    sub_html = f"<div class='kpi-sub'>{sub}</div>" if sub else ""
    return (f"<div class='kpi' style='--accent:{hexc}'>"
            f"<div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value' style='color:{hexc}'>{value}</div>{sub_html}</div>")


def badge(text, kind="green") -> str:
    return f"<span class='badge badge-{kind}'>{text}</span>"


def alert(text, kind="coral", icon="⚠️", flash=False) -> str:
    fl = " alert-flash" if flash else ""
    return f"<div class='alert alert-{kind}{fl}'><span style='font-size:1.3rem'>{icon}</span><span>{text}</span></div>"


def headline(title, sub="", accent="blue", icon="•") -> str:
    hexc = PALETTE.get(accent, PALETTE["blue"])
    sub_html = f"<div class='h-sub'>{sub}</div>" if sub else ""
    return (f"<div class='headline' style='--accent:{hexc}'>"
            f"<span style='font-size:1.3rem'>{icon}</span>"
            f"<div><div class='h-title'>{title}</div>{sub_html}</div></div>")


def section_label(text) -> str:
    return f"<div class='section-label'>{text}</div>"


def glow_block(value, label) -> str:
    return f"<div class='glow-block'><div class='gb-label'>{label}</div><div class='gb-value'>{value}</div></div>"
```

================================================================
FILE: core/auth.py
================================================================
```python
"""
core/auth.py
============
SHA-256 session-state login gate. Blocks the whole app until authenticated.

Demo credentials:  admin / your local password
(For production, move the hash to Settings/env and add rate limiting.)
"""

from __future__ import annotations
import hashlib
import streamlit as st

from core.styles import inject_global_css


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_VALID_HASHES = {_hash("admin|your local password")}


def _verify(username: str, password: str) -> bool:
    return _hash(f"{username.strip()}|{password}") in _VALID_HASHES


def is_authenticated() -> bool:
    return bool(st.session_state.get("authenticated", False))


def logout() -> None:
    st.session_state["authenticated"] = False
    st.session_state.pop("username", None)
    st.rerun()


def login_gate() -> bool:
    """Return True if authenticated; otherwise render login card and return False."""
    if is_authenticated():
        return True

    inject_global_css()
    st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.15, 1])
    with mid:
        st.markdown(
            "<div class='glass-card' style='padding:34px 34px 26px;'>"
            "<div class='login-hero'><div class='lh-logo'>🛒</div>"
            "<div class='lh-title'>Amazon.ae Seller Command</div>"
            "<div class='lh-sub'>Local-First Operations Dashboard</div></div>",
            unsafe_allow_html=True)
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="••••••••••")
            submitted = st.form_submit_button("🔓  Sign In", use_container_width=True)
        if submitted:
            if _verify(username, password):
                st.session_state["authenticated"] = True
                st.session_state["username"] = username.strip()
                st.rerun()
            else:
                st.markdown(
                    "<div class='alert alert-coral'><span style='font-size:1.3rem'>⛔</span>"
                    "<span>Invalid credentials.</span></div>", unsafe_allow_html=True)
        st.markdown(
            "<div style='text-align:center; color:var(--muted); font-size:.78rem; margin-top:14px'>"
            "🔒 SHA-256 verified · local session</div></div>", unsafe_allow_html=True)
    return False
```

================================================================
FILE: core/components.py
================================================================
```python
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
```

================================================================
FILE: core/util.py
================================================================
```python
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
```

================================================================
FILE: core/assistant.py
================================================================
```python
"""
core/assistant.py
=================
In-dashboard conversational AI assistant.

It builds a LIVE context snapshot from the DB + api_client (open tasks,
out-of-stock count, lost buyboxes, campaign budget alerts, profit summary) and
sends it to the Anthropic API (model from MODEL constant) so answers reflect the
seller's real operation. If no API key is configured in Settings, it falls back
to a rule-based responder so the demo always works offline.

The same answer() function powers both the full AI Assistant page and the
sidebar quick-ask box. Conversation history is persisted in SQLite (db.chat_*).
"""

from __future__ import annotations

from core import db, mock_data
from core.api_client import client

# Model id specified by the project owner.
MODEL = "claude-opus-4-20250514"


# ---------------------------------------------------------------------------
# Live context
# ---------------------------------------------------------------------------
def build_context() -> dict:
    """Snapshot the real operational state for grounding the assistant."""
    api = client()
    listings = api.get_my_listings()
    campaigns = api.get_campaigns()
    buybox = api.get_lost_buybox()
    orders = api.get_orders()

    oos = listings[listings["fba_stock"] == 0]["title"].tolist()
    over_budget = campaigns[campaigns["spend_today"] > campaigns["avg_daily"] * 1.2]["campaign"].tolist()
    profit = float((orders["revenue"] - orders["cost"] - orders["ad_spend"]).sum())

    return {
        "open_tasks": [t["title"] for t in db.get_tasks("open")[:10]],
        "out_of_stock": oos,
        "lost_buyboxes": buybox["title"].tolist(),
        "campaigns_over_budget": over_budget,
        "total_profit": round(profit, 2),
    }


def _context_text(ctx: dict) -> str:
    return (
        f"Open tasks: {', '.join(ctx['open_tasks']) or 'none'}\n"
        f"Out of stock: {', '.join(ctx['out_of_stock']) or 'none'}\n"
        f"Lost buyboxes: {', '.join(ctx['lost_buyboxes']) or 'none'}\n"
        f"Campaigns over budget: {', '.join(ctx['campaigns_over_budget']) or 'none'}\n"
        f"Total profit (period): AED {ctx['total_profit']:,.2f}"
    )


# ---------------------------------------------------------------------------
# Answer routing: Anthropic if key present, else rule-based
# ---------------------------------------------------------------------------
def answer(prompt: str) -> str:
    ctx = build_context()
    api_key = db.get_setting("anthropic_api_key", "")
    if api_key:
        try:
            return _anthropic_answer(prompt, ctx, api_key)
        except Exception as e:
            return (f"⚠️ Anthropic call failed ({e}). Falling back to local analysis.\n\n"
                    + _rule_based(prompt, ctx))
    return _rule_based(prompt, ctx)


def complete(system_prompt: str, user_prompt: str, max_tokens: int = 12000) -> tuple[str | None, str]:
    """Generic one-shot long-form completion (used by the A+ Content Studio).

    Returns (text, status). status is 'ok' | 'no_key' | 'error: ...'.
    text is None unless status == 'ok'. Requires an Anthropic key in Settings.
    """
    key = db.get_setting("anthropic_api_key", "")
    if not key:
        return None, "no_key"
    try:
        import anthropic
        c = anthropic.Anthropic(api_key=key)
        resp = c.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(b.text for b in resp.content if hasattr(b, "text")), "ok"
    except Exception as e:
        return None, f"error: {e}"


def _anthropic_answer(prompt: str, ctx: dict, api_key: str) -> str:
    """Real Claude call. Imported lazily so the package is optional."""
    import anthropic
    cclient = anthropic.Anthropic(api_key=api_key)
    system = (
        "You are an embedded operations assistant for a single Amazon.ae seller. "
        "Use the LIVE CONTEXT to give specific, actionable advice. Be concise and "
        "practical. Never claim to have changed prices or listings — only suggest. "
        "If asked to take an action, describe the exact step the seller should confirm.\n\n"
        f"LIVE CONTEXT:\n{_context_text(ctx)}"
    )
    resp = cclient.messages.create(
        model=MODEL, max_tokens=900, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in resp.content if hasattr(block, "text"))


def _rule_based(prompt: str, ctx: dict) -> str:
    """Offline fallback that still reads the live context."""
    p = prompt.lower()
    if any(k in p for k in ["today", "focus", "priority", "what should", "work on"]):
        return (f"**Today's priorities**\n\n"
                f"1. {len(ctx['out_of_stock'])} out of stock: {', '.join(ctx['out_of_stock']) or '—'}\n"
                f"2. {len(ctx['lost_buyboxes'])} lost buyboxes: {', '.join(ctx['lost_buyboxes']) or '—'}\n"
                f"3. {len(ctx['campaigns_over_budget'])} campaigns over budget\n"
                f"4. {len(ctx['open_tasks'])} open tasks in your feed\n\n"
                f"Start with out-of-stock — every hour costs sales.")
    if any(k in p for k in ["losing money", "loss", "profit", "margin"]):
        return (f"Period profit is **AED {ctx['total_profit']:,.2f}**. Check the Orders & "
                f"Profit page for the bottom-3 items; items with high ad spend and low "
                f"revenue are your margin leaks.")
    if any(k in p for k in ["buybox", "price"]):
        return (f"Lost buyboxes: {', '.join(ctx['lost_buyboxes']) or 'none'}. Open Pricing → "
                f"Lost Buybox to see competitor prices and decide whether to match.")
    if any(k in p for k in ["stock", "inventory", "restock"]):
        return (f"Out of stock: {', '.join(ctx['out_of_stock']) or 'none'}. Use Stock "
                f"Management to compute ship quantities from velocity.")
    if any(k in p for k in ["ad", "campaign", "budget"]):
        return (f"Over-budget campaigns: {', '.join(ctx['campaigns_over_budget']) or 'none'}. "
                f"Cap their daily budget on the Advertising page.")
    return ("I can help with **priorities**, **profit/margins**, **buybox/pricing**, "
            "**stock**, or **ads**. Add an Anthropic API key in Settings for full "
            "conversational answers about ASINs, titles and strategy.")
```

================================================================
FILE: core/imagegen.py
================================================================
```python
"""
core/imagegen.py
================
Image generation layer for the A+ Content Studio.

Claude writes the gpt-image prompts; THIS module turns them into actual images by
calling the OpenAI image API (default model 'gpt-image-1', configurable in
Settings). When you upload one or more product reference images, they are passed
to the images.edit endpoint so the generated scene keeps the product's identity;
with no reference image it falls back to images.generate.

Key + model come from Settings (DB). Every call returns (png_bytes|None, status)
and never raises into the UI.

Note: the public image API renders up to 1536px; the A+ prompts ask for 2000px so
the designer upscales/crops after. Choose 1024x1024 (1:1) here to match the A+
square ratio.
"""

from __future__ import annotations
import io
import base64

from core import db

# Sizes the OpenAI image API supports (square first = matches A+ 1:1).
SUPPORTED_SIZES = ["1024x1024", "1536x1024", "1024x1536"]
DEFAULT_MODEL = "gpt-image-1"


def image_model() -> str:
    return db.get_setting("image_model", DEFAULT_MODEL) or DEFAULT_MODEL


def has_image_key() -> bool:
    return bool(db.get_setting("openai_api_key", ""))


def generate_image(prompt: str, reference_images: list[bytes] | None = None,
                   size: str = "1024x1024") -> tuple[bytes | None, str]:
    """Generate one image from a prompt (+ optional reference images).

    reference_images: list of raw image bytes (PNG/JPG). If provided, uses the
    edit endpoint so the product identity is preserved.
    Returns (png_bytes, status). status: 'ok' | 'no_key' | 'error: ...'.
    """
    key = db.get_setting("openai_api_key", "")
    if not key:
        return None, "no_key"
    model = image_model()
    try:
        import openai
        client = openai.OpenAI(api_key=key)
        if reference_images:
            files = []
            for i, b in enumerate(reference_images):
                bio = io.BytesIO(b)
                bio.name = f"reference_{i}.png"
                files.append(bio)
            resp = client.images.edit(
                model=model,
                image=files if len(files) > 1 else files[0],
                prompt=prompt,
                size=size,
            )
        else:
            resp = client.images.generate(model=model, prompt=prompt, size=size)

        item = resp.data[0]
        # gpt-image-1 returns base64; some models/paths may return a URL.
        if getattr(item, "b64_json", None):
            return base64.b64decode(item.b64_json), "ok"
        if getattr(item, "url", None):
            import requests
            r = requests.get(item.url, timeout=30)
            return r.content, "ok"
        return None, "error: no image data returned"
    except Exception as e:
        return None, f"error: {e}"
```

================================================================
FILE: modules/__init__.py
================================================================
```python
"""Page modules — one file per dashboard section (13 functional + AI assistant)."""
```

================================================================
FILE: modules/home.py
================================================================
```python
"""
modules/home.py
===============
🏠 Home — Daily Action Center.

Aggregates the most important signals from every module into headline KPI cards
and a single prioritized task feed (read from the central Tasks table). Each task
row has a "Go" button that navigates to its related section.

regenerate_tasks() scans all modules' (mock) data + e-commerce best practices and
writes tasks into the DB; it runs once per session and can be re-run on demand.
"""

from __future__ import annotations
import streamlit as st

from core import db
from core.api_client import client
from core.components import kpi_row, page_header
from core.styles import headline, alert, section_label


def regenerate_tasks() -> None:
    """Scan all data sources and (re)populate the central Tasks table."""
    db.clear_tasks()
    api = client()
    listings = api.get_my_listings()
    campaigns = api.get_campaigns()
    buybox = api.get_lost_buybox()
    market = api.get_market_comparison()
    events = api.get_events()
    catalog_skus = db.get_catalog_skus()

    # Out of stock
    for _, r in listings[listings["fba_stock"] == 0].iterrows():
        db.add_task(f"Restock OUT-OF-STOCK: {r['title']}",
                    f"Selling {r['daily_velocity']}/day with 0 units.",
                    module="Stock Management", priority="high", related_id=r["sku"])
    # Below threshold
    for _, r in listings[(listings["fba_stock"] > 0) &
                         (listings["fba_stock"] < listings["daily_velocity"] * 10)].iterrows():
        db.add_task(f"Low stock: {r['title']}",
                    f"{r['fba_stock']} units left (~{r['fba_stock']/max(r['daily_velocity'],0.1):.0f} days).",
                    module="Stock Management", priority="medium", related_id=r["sku"])
    # Lost buybox
    for _, r in buybox.iterrows():
        db.add_task(f"Lost buybox: {r['title']}",
                    f"Competitor {r['buybox_winner']} at AED {r['buybox_price']} vs your AED {r['your_price']}.",
                    module="Pricing", priority="high", related_id=r["sku"])
    # Over budget campaigns
    for _, r in campaigns[campaigns["spend_today"] > campaigns["avg_daily"] * 1.2].iterrows():
        db.add_task(f"Campaign over budget: {r['campaign']}",
                    f"AED {r['spend_today']} vs AED {r['avg_daily']} avg.",
                    module="Advertising", priority="medium", related_id=r["campaign"])
    # Trending + well priced → promote
    for _, r in market[market["signal"].isin(["Trending", "Hidden Gem"])].iterrows():
        db.add_task(f"Promote trending item: {r['item']}",
                    f"{r['signal']} with {r['monthly_demand']:,} monthly demand — add A+ content & ads.",
                    module="Market Analysis", priority="medium", related_id=r["item"])
    # New arrivals to list (warehouse items not in catalog handled in intake;
    # here we surface the count as a task)
    from core import inventory_source
    inv, _ = inventory_source.fetch_inventory()
    if not inv.empty:
        new_n = int((~inv["sku"].isin(catalog_skus)).sum())
        if new_n:
            db.add_task(f"List {new_n} new arrivals on Amazon",
                        "New warehouse items not yet in your catalog.",
                        module="Inventory & Listing Intake", priority="high")
    # Upcoming events
    for _, r in events.head(2).iterrows():
        db.add_task(f"Prepare for event: {r['event']} ({r['date']})",
                    r["action"], module="Event Planner", priority="low")


def render(nav) -> None:
    page_header("Daily Action Center",
                "Everything that needs your attention today, in priority order", icon="🏠")

    # Regenerate once per session unless asked.
    if "tasks_seeded" not in st.session_state:
        regenerate_tasks()
        st.session_state["tasks_seeded"] = True

    api = client()
    listings = api.get_my_listings()
    campaigns = api.get_campaigns()
    buybox = api.get_lost_buybox()
    from core import inventory_source
    inv, _ = inventory_source.fetch_inventory()
    new_to_list = int((~inv["sku"].isin(db.get_catalog_skus())).sum()) if not inv.empty else 0

    kpi_row([
        {"label": "Items to List", "value": str(new_to_list), "accent": "emerald",
         "sub": "New arrivals pending"},
        {"label": "Out of Stock", "value": str(int((listings["fba_stock"] == 0).sum())),
         "accent": "coral", "sub": "Live ASINs at zero"},
        {"label": "Lost Buyboxes", "value": str(len(buybox)), "accent": "coral",
         "sub": "Due to competitor price"},
        {"label": "Campaigns Over Budget",
         "value": str(int((campaigns["spend_today"] > campaigns["avg_daily"] * 1.2).sum())),
         "accent": "violet", "sub": ">20% above daily avg"},
    ])

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    top = st.columns([3, 1])
    with top[0]:
        st.markdown(section_label("⚡ Prioritized Task Feed"), unsafe_allow_html=True)
    with top[1]:
        if st.button("🔄 Rescan", use_container_width=True):
            regenerate_tasks()
            st.rerun()

    tasks = db.get_tasks("open")
    if not tasks:
        st.markdown(alert("All clear — no open tasks.", kind="green", icon="✅"),
                    unsafe_allow_html=True)
        return

    accent_map = {"high": "coral", "medium": "amber", "low": "blue"}
    icon_map = {"high": "🔴", "medium": "🟠", "low": "🔵"}
    for t in tasks:
        c1, c2, c3 = st.columns([6, 1.4, 1])
        with c1:
            st.markdown(
                headline(t["title"], t["detail"],
                         accent=accent_map.get(t["priority"], "blue"),
                         icon=icon_map.get(t["priority"], "•")),
                unsafe_allow_html=True)
        with c2:
            if t["module"] and st.button(f"↪ {t['module'].split()[0]}", key=f"go_{t['id']}",
                                         use_container_width=True):
                nav(t["module"])
        with c3:
            if st.button("✓ Done", key=f"done_{t['id']}", use_container_width=True):
                db.complete_task(t["id"])
                st.rerun()
```

================================================================
FILE: modules/intake.py
================================================================
```python
"""
modules/intake.py
=================
📥 Inventory & Listing Intake + Auto Item Creation (Module 2).

Sub-tabs:
  1. New Arrivals    — warehouse items not in your Amazon catalog (Mark as listed)
  2. Restock Pending — catalogued items needing replenishment
  3. Auto Item Creation:
        MODE A (price list): upload CSV/Excel w/ media-link column → fetch images,
                              take price from file.
        MODE B (URL): paste item URLs → generic scrape (title/price/specs/images).
        Both → build draft → optimize copy → REVIEW TABLE (editable) → Approve →
        "Ready to List" queue (persisted in DB), with Export.

Fetching is routed through oskar_source (USE_MOCK now). Listing copy via the
optimization module. Flagged rows (no price / no image) get an amber badge.
"""

from __future__ import annotations
import re
import io
import json
import pandas as pd
import streamlit as st

from core import db, inventory_source, oskar_source
from core.api_client import client
from core.util import get_field, find_column
from core.components import styled_table, export_buttons, page_header
from core.styles import section_label, badge, alert
from modules import optimization


def _classify(inv: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split inventory into new arrivals vs restock by comparing to the catalog."""
    catalog = db.get_catalog_skus()
    inv = inv.copy()
    new = inv[~inv["sku"].isin(catalog)].copy()
    restock = inv[inv["sku"].isin(catalog)].copy()
    return new.reset_index(drop=True), restock.reset_index(drop=True)


def _new_arrivals_tab() -> None:
    st.markdown(section_label("Fetch from inventory website (or upload below)"),
                unsafe_allow_html=True)
    up = st.file_uploader("Manual fallback: upload product list (CSV/Excel)",
                          type=["csv", "xlsx"], key="intake_upload")

    if up:
        inv = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
        # Normalize to expected columns via fuzzy detection.
        inv = pd.DataFrame({
            "sku": get_field(inv, "sku", ""), "title": get_field(inv, "title", ""),
            "brand": get_field(inv, "brand", ""), "category": get_field(inv, "category", ""),
            "warehouse_qty": get_field(inv, "qty", 0), "cost": get_field(inv, "price", 0),
        })
        src = f"uploaded file ({up.name})"
    else:
        inv, src = inventory_source.fetch_inventory()

    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)
    if inv.empty:
        st.warning("No inventory returned.")
        return

    new, _ = _classify(inv)
    st.markdown(f"<p style='color:var(--muted)'>{len(new)} items not yet in your Amazon "
                f"catalog.</p>", unsafe_allow_html=True)

    # Optional brand filter.
    brands = ["All"] + sorted(new["brand"].dropna().unique().tolist())
    pick = st.selectbox("Filter by brand", brands, key="na_brand")
    view = new if pick == "All" else new[new["brand"] == pick]

    styled_table(view, highlight={"row-good": lambda r: True})
    export_buttons(view, "new_arrivals")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    cols = st.columns([3, 1])
    with cols[0]:
        to_list = st.multiselect("Select SKUs to mark as listed", view["sku"].tolist(),
                                 key="na_marklist")
    with cols[1]:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("✅ Mark as Listed", use_container_width=True) and to_list:
            for sku in to_list:
                row = view[view["sku"] == sku].iloc[0]
                db.upsert_catalog_item(sku=sku, title=row["title"], brand=row["brand"],
                                       category=row["category"], status="listed")
                db.add_task(f"Verify new listing live: {row['title']}",
                            "Marked as listed from intake.",
                            module="Inventory & Listing Intake", priority="low",
                            related_id=sku)
            st.success(f"Marked {len(to_list)} item(s) as listed and logged tasks.")
            st.rerun()


def _restock_tab() -> None:
    inv, src = inventory_source.fetch_inventory()
    if inv.empty:
        st.info("No inventory source available.")
        return
    _, restock = _classify(inv)
    # Join velocity from listings to show urgency.
    from core.api_client import client
    listings = client().get_my_listings()[["sku", "fba_stock", "daily_velocity"]]
    merged = restock.merge(listings, on="sku", how="left").fillna({"fba_stock": 0, "daily_velocity": 0})
    merged["days_left"] = (merged["fba_stock"] / merged["daily_velocity"].replace(0, 0.1)).round(1)
    merged["needs_restock"] = merged["fba_stock"] < merged["daily_velocity"] * 10
    overrides = db.get_channel_overrides()  # FBA/FBM decisions from Hazmat
    merged["channel"] = merged["sku"].map(lambda s: overrides.get(s, "FBA"))

    st.markdown(f"<p style='color:var(--muted)'>{int(merged['needs_restock'].sum())} catalogued "
                f"items below a 10-day stock cover. <span style='color:var(--muted)'>FBM items "
                f"don't need FBA restock.</span></p>", unsafe_allow_html=True)
    styled_table(
        merged[["sku", "title", "brand", "channel", "fba_stock", "daily_velocity", "days_left", "warehouse_qty"]],
        highlight={"row-danger": lambda r: r["fba_stock"] == 0 and r["channel"] == "FBA",
                   "row-warn": lambda r: 0 < r["fba_stock"] < r["daily_velocity"] * 10},
        badge_cols={"channel": {"FBA": ("FBA", "blue"), "FBM": ("FBM", "violet")}})
    export_buttons(merged, "restock_pending")


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(text)).strip("-")[:24] or "ITEM"


def _guess_product_type(title: str) -> str:
    t = (title or "").lower()
    rules = [("POWER_BANK", ["power bank", "powerbank", "power core"]),
             ("HEADPHONES", ["earbud", "headphone", "airpods", "earphone", "buds"]),
             ("SPEAKERS", ["speaker", "soundbar", "partybox", "boombox"]),
             ("CHARGER", ["charger", "charging", "gan", "adapter"]),
             ("PHONE_CASE", ["case", "cover", "sleeve"]),
             ("CAMERA", ["camera", "cam"]),
             ("SMARTWATCH", ["watch", "smartwatch", "band"])]
    for pt, kws in rules:
        if any(k in t for k in kws):
            return pt
    return "GENERIC"


# Price-list columns we auto-map to Amazon attribute names (beyond sku/title/price).
_EXTRA_MAP = {
    "color": ["color", "colour"],
    "model_number": ["model", "model number", "model no", "mpn", "modelnumber"],
    "product_description": ["description", "desc", "long description", "details"],
    "bullet_point": ["bullet", "bullets", "features", "key features", "highlights"],
    "external_product_id": ["barcode", "upc", "ean", "gtin"],
    "watt_hours": ["watt hours", "wh", "watt-hours", "watthours"],
    "wattage": ["wattage", "power", "watt"],
    "material": ["material"],
    "connectivity_technology": ["connectivity", "connection", "connectivity technology"],
    "screen_size": ["screen size", "display size", "screen"],
    "compatible_devices": ["compatible", "compatibility", "compatible devices"],
}


def _inorm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _normalize_barcode(raw) -> str:
    """Barcode rule from the price list:
       - if it STARTS WITH 0  -> remove the leading 0
       - otherwise            -> remove the last digit
    Handles values read as numbers (e.g. 6291100.0) by stripping to digits first.
    """
    if raw is None:
        return ""
    s = str(raw).strip()
    if s.endswith(".0"):          # pandas may read the code as a float
        s = s[:-2]
    s = re.sub(r"\D", "", s)        # keep digits only
    if not s:
        return ""
    return s[1:] if s.startswith("0") else s[:-1]


def _parse_battery(feature_text) -> dict:
    """Extract battery energy/mAh/voltage from the Feature spec text so lithium
    fields auto-fill (e.g. 'Battery Capacity: 4000mAh (3.7V / 14.8Wh)')."""
    t = str(feature_text or "")
    out = {}
    # Negative lookbehind for a letter so a SKU like 'PDLFSTF608WH' isn't read as 608Wh.
    m = re.search(r"(?<![A-Za-z])([\d.]+)\s*wh\b", t, re.I)
    if m:
        out["lithium_energy"] = float(m.group(1))
    mah = re.search(r"(?<![A-Za-z])([\d.]+)\s*mah\b", t, re.I)
    if mah:
        out["mah"] = float(mah.group(1))
    v = re.search(r"(?<![A-Za-z])([\d.]+)\s*v\b", t, re.I)
    if v:
        out["voltage"] = float(v.group(1))
    # Estimate Wh from mAh × V if Wh wasn't stated.
    if "lithium_energy" not in out and "mah" in out:
        out["lithium_energy"] = round(out["mah"] / 1000.0 * out.get("voltage", 3.7), 2)
    if re.search(r"lithium|li-?ion|li-?po|rechargeable|mah", t, re.I):
        out["has_battery"] = True
    return out


def _extra_colmap(df: pd.DataFrame) -> dict:
    """Map Amazon-field -> dataframe column for whatever the price list contains."""
    norm = {_inorm(c): c for c in df.columns}
    out = {}
    for field, aliases in _EXTRA_MAP.items():
        for a in aliases:
            if _inorm(a) in norm:
                out[field] = norm[_inorm(a)]
                break
        else:
            for a in aliases:
                hit = next((orig for nc, orig in norm.items() if _inorm(a) in nc), None)
                if hit:
                    out[field] = hit
                    break
    return out


def _brand_defaults() -> dict:
    return {
        "brand_owner": db.get_setting("brand_owner_mode", "0") == "1",
        "brand": db.get_setting("default_brand", ""),
        "manufacturer": db.get_setting("default_manufacturer", ""),
        "country": db.get_setting("default_country_of_origin", "China"),
    }


def _apply_defaults(draft: dict) -> dict:
    d = dict(draft)
    bd = _brand_defaults()
    if not str(d.get("brand", "")).strip():
        d["brand"] = bd["brand"]
    d.setdefault("extra", {})
    return d


def _relax_for_brand_owner(reqs: list) -> list:
    """Brand owners are GTIN-exempt → barcode fields become optional."""
    if not _brand_defaults()["brand_owner"]:
        return reqs
    out = []
    for f in reqs:
        g = dict(f)
        if g["name"] in ("external_product_id", "external_product_id_type"):
            g["required"] = False
        out.append(g)
    return out


# Amazon attribute names already handled by our curated CORE fields (so we don't
# render them twice when merging with the live schema).
_CORE_COVERED = {
    "item_name", "brand", "manufacturer", "bullet_point", "product_description",
    "color", "color_name", "country_of_origin", "condition_type",
    "external_product_id", "externally_assigned_product_identifier",
    "external_product_id_type", "list_price", "purchasable_offer", "standard_price",
    "fulfillment_availability", "quantity", "main_image_url",
    "main_product_image_locator", "merchant_suggested_asin",
    "parentage_level", "variation_theme", "child_relationship_type",
}


# Smart defaults for category fields Amazon commonly enforces (so they auto-fill).
_SMART_DEFAULTS = {
    "model_number": lambda d: d.get("sku", ""),
    "oem_equivalent_part_number": lambda d: d.get("sku", ""),
    "part_number": lambda d: d.get("sku", ""),
    "manufacturer_part_number": lambda d: d.get("sku", ""),
    "warranty_description": lambda d: "1 Year Manufacturer Warranty",
    "seller_warranty_description": lambda d: "1 Year Manufacturer Warranty",
    "included_components": lambda d: "Device, USB-C Charging Cable, User Manual",
    "supplier_declared_dg_hz_regulation": lambda d: "not_applicable",
    "is_oem_authorized": lambda d: "true",
    "is_oem_sourced_product": lambda d: "false",
    "power_plug_type": lambda d: "no_plug",
    "accepted_voltage_frequency": lambda d: "100v_240v_50hz_60hz",
    "shipping_weight_unit": lambda d: "kilograms",
    "dimension_unit": lambda d: "centimeters",
    "package_weight_unit": lambda d: "kilograms",
    "package_dimension_unit": lambda d: "centimeters",
    "number_of_items": lambda d: 1,
    "number_of_boxes": lambda d: 1,
    "required_assembly": lambda d: "No",
    # Battery defaults (electronics with a built-in Li-ion battery).
    "batteries_required": lambda d: "true",
    "batteries_included": lambda d: "true",
    "has_multiple_battery_powered_components": lambda d: "false",
    "contains_battery_or_cell": lambda d: "battery",
    "number_of_lithium_ion_cells": lambda d: 1,
    "number_of_batteries": lambda d: 1,
    "battery_cell_composition": lambda d: "lithium_ion",
    "battery_type": lambda d: "nonstandard_battery",
    "battery_installation_device_type": lambda d: "installed_in_equipment",
    "lithium_packaging": lambda d: "batteries_contained_in_equipment",
    "lithium_energy_unit": lambda d: "watt_hours",
    "battery_weight_unit": lambda d: "kilograms",
    "lithium_weight_unit": lambda d: "kilograms",
}

# Nested attributes → expand into simple value/unit form fields (mapped back in sp_api).
_NESTED_FIELDS = {
    "website_shipping_weight": [
        {"name": "shipping_weight", "label": "Shipping weight", "type": "number", "required": True},
        {"name": "shipping_weight_unit", "label": "Weight unit", "type": "select",
         "options": ["kilograms", "grams", "pounds", "ounces"], "required": True,
         "default": "kilograms"},
    ],
    "item_depth_width_height": [
        {"name": "item_length", "label": "Item length (depth)", "type": "number", "required": True},
        {"name": "item_width", "label": "Item width", "type": "number", "required": True},
        {"name": "item_height", "label": "Item height", "type": "number", "required": True},
        {"name": "dimension_unit", "label": "Item dimension unit", "type": "select",
         "options": ["centimeters", "inches"], "required": True, "default": "centimeters"},
    ],
    "item_package_weight": [
        {"name": "package_weight", "label": "Package weight", "type": "number", "required": True},
        {"name": "package_weight_unit", "label": "Package weight unit", "type": "select",
         "options": ["kilograms", "grams", "pounds", "ounces"], "required": True,
         "default": "kilograms"},
    ],
    "item_package_dimensions": [
        {"name": "package_length", "label": "Package length", "type": "number", "required": True},
        {"name": "package_width", "label": "Package width", "type": "number", "required": True},
        {"name": "package_height", "label": "Package height", "type": "number", "required": True},
        {"name": "package_dimension_unit", "label": "Package dimension unit", "type": "select",
         "options": ["centimeters", "inches"], "required": True, "default": "centimeters"},
    ],
    "battery": [
        {"name": "battery_cell_composition", "label": "Battery cell composition", "type": "select",
         "options": ["lithium_ion", "lithium_polymer", "lithium_metal", "alkaline",
                     "NiMh", "NiCAD", "lead_acid"], "required": True, "default": "lithium_ion"},
        {"name": "battery_weight", "label": "Battery weight", "type": "number", "required": True},
        {"name": "battery_weight_unit", "label": "Battery weight unit", "type": "select",
         "options": ["kilograms", "grams", "ounces", "pounds"], "required": True,
         "default": "kilograms"},
    ],
    "lithium_battery": [
        {"name": "lithium_energy", "label": "Lithium energy content (Wh)", "type": "number",
         "required": True},
        {"name": "lithium_energy_unit", "label": "Energy unit", "type": "select",
         "options": ["watt_hours", "milliampere_hour", "kilowatt_hours"], "required": True,
         "default": "watt_hours"},
        {"name": "lithium_packaging", "label": "Lithium packaging", "type": "select",
         "options": ["batteries_contained_in_equipment", "batteries_packed_with_equipment",
                     "batteries_only"], "required": True,
         "default": "batteries_contained_in_equipment"},
        {"name": "lithium_weight", "label": "Lithium battery weight", "type": "number",
         "required": True},
        {"name": "lithium_weight_unit", "label": "Lithium weight unit", "type": "select",
         "options": ["kilograms", "grams", "ounces"], "required": True, "default": "kilograms"},
    ],
    "num_batteries": [
        {"name": "number_of_batteries", "label": "Number of batteries", "type": "number",
         "required": True, "default": 1},
        {"name": "battery_type", "label": "Battery type", "type": "select",
         "options": ["nonstandard_battery", "aa", "aaa", "9v", "lithium_ion"], "required": True,
         "default": "nonstandard_battery"},
    ],
    "battery_installation_device_type": [
        {"name": "battery_installation_device_type", "label": "Battery installation", "type": "select",
         "options": ["installed_in_equipment", "not_installed", "installed_in_vehicle",
                     "installed_in_vessel"], "required": True, "default": "installed_in_equipment"},
    ],
}


def _core_fields() -> list:
    """Our curated set that auto-fills + maps to SP-API correctly (item_name,
    brand, bullets, description, price, qty, barcode, image, colour, channel…)."""
    from core import mock_data
    fields = [dict(f) for f in mock_data.listing_requirements("GENERIC")]
    if not any(f["name"] == "color" for f in fields):
        fields.append({"name": "color", "label": "Color", "required": True, "type": "text"})
    return fields


def _expand_field(name: str, full_by_name: dict) -> list:
    """Turn an Amazon attribute name into renderable form field(s)."""
    if name in _NESTED_FIELDS:
        return [dict(f) for f in _NESTED_FIELDS[name]]
    f = full_by_name.get(name)
    if f:
        return [dict(f)]
    # not in schema (rare) — render a generic text field
    return [{"name": name, "label": name.replace("_", " ").title(),
             "required": True, "type": "text"}]


def _hybrid_requirements(pt: str) -> list:
    """LIVE form = curated CORE (auto-filled) + Amazon's required fields not in CORE
    + any fields discovered from a previous validation — with nested fields expanded
    into simple value/unit inputs and smart defaults applied."""
    core = _core_fields()
    covered = set(_CORE_COVERED) | {f["name"] for f in core}
    try:
        live = client().get_listing_requirements(pt)
    except Exception:
        return core
    full_by_name = {f["name"]: f for f in live}
    discovered = st.session_state.get("aic_more", {}).get(pt, set())
    need = [f["name"] for f in live if f.get("required")] + list(discovered)
    extra, seen = [], set()
    for name in need:
        if name in covered or name in seen:
            continue
        seen.add(name)
        for fld in _expand_field(name, full_by_name):
            if fld["name"] not in covered:
                extra.append(fld)
    return core + extra


def _prefill(field: dict, draft: dict, opt: dict):
    """Pre-fill a field from price-list extras, fetched draft, optimized copy, defaults."""
    name = field["name"]
    extra = draft.get("extra", {})
    if name in extra and str(extra[name]).strip():
        return extra[name]
    bd = _brand_defaults()
    if name == "manufacturer":
        return draft.get("brand") or bd["manufacturer"] or bd["brand"]
    if name == "country_of_origin":
        return bd["country"] or field.get("default", "")
    src = field.get("source")
    if src == "title":
        return opt.get("title", draft.get("title", ""))
    if src == "bullets":
        return "\n".join(opt.get("bullets", []))
    if src == "description":
        return opt.get("description", "")
    if src == "brand":
        return draft.get("brand", "")
    if src == "price":
        p = draft.get("price")
        return float(p) if p not in (None, "", 0) and not pd.isna(p) else 0.0
    if src == "image":
        imgs = draft.get("images") or []
        return imgs[0] if imgs else ""
    if name in _SMART_DEFAULTS:
        return _SMART_DEFAULTS[name](draft)
    return field.get("default", "")


# ---------------------------------------------------------------------------
# Smart price-list parser (handles formatted sheets: header not on row 1,
# section/category rows, multi-price columns, hyperlinked media/image cells).
# ---------------------------------------------------------------------------
_PL_ALIASES = {
    "sku": ["sku", "seller sku", "item code", "code", "model"],
    "title": ["product name", "title", "name", "product", "item name"],
    "feature": ["feature", "features", "specification", "specs", "details", "description"],
    "color": ["color", "colour"],
    "barcode": ["barcode", "ean", "upc", "gtin"],
    "price_rrp": ["rrp", "rrpaed", "recommended"],
    "price_mrp": ["mrp", "mrpaed"],
    "price_base": ["price", "priceaed", "unit price", "selling price"],
    "media": ["media", "media link", "medialink"],
    "image": ["image", "mockup", "photo", "picture"],
    "carton": ["carton", "carton details", "packaging"],
}


def _pnorm(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def _detect_header_and_map(raw: pd.DataFrame) -> tuple:
    """Find the header row and map logical fields → column index."""
    best = (None, -1, {})
    for ri in range(min(len(raw), 15)):
        colmap = {}
        for ci in range(raw.shape[1]):
            cell = _pnorm(raw.iat[ri, ci])
            if not cell:
                continue
            for field, aliases in _PL_ALIASES.items():
                if field in colmap:
                    continue
                if any(cell == _pnorm(a) or _pnorm(a) in cell for a in aliases):
                    colmap[field] = ci
        if len(colmap) > best[1]:
            best = (ri, len(colmap), colmap)
    hidx, score, colmap = best
    return (hidx if score >= 3 else None), colmap


def _clean_feature(s) -> list:
    """Split a Feature cell into clean lines (fix mangled bullet/encoding chars)."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    txt = str(s)
    for junk in ["�", "•", "▪", "●", "·", "*"]:
        txt = txt.replace(junk, "\n")
    lines = re.split(r"[\n\r]+", txt)
    out = []
    for ln in lines:
        ln = re.sub(r"^[^A-Za-z0-9]+", "", ln).strip()
        if len(ln) > 1:
            out.append(ln)
    return out


def _parse_pricelist_bytes(data: bytes, is_csv: bool) -> pd.DataFrame:
    """Return a normalized DataFrame: sku,title,feature,color,price,barcode,media,image."""
    if is_csv:
        raw = pd.read_csv(io.BytesIO(data), header=None, dtype=str)
        ws = None
    else:
        raw = pd.read_excel(io.BytesIO(data), header=None, dtype=str)
        try:
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(data))
            ws = wb[wb.sheetnames[0]]
        except Exception:
            ws = None

    hidx, colmap = _detect_header_and_map(raw)
    if hidx is None:
        hidx, colmap = 0, _detect_header_and_map(raw)[1]
    price_col = colmap.get("price_rrp")  # user chose RRP
    if price_col is None:
        price_col = colmap.get("price_mrp")
    if price_col is None:
        price_col = colmap.get("price_base")

    def cell_at(ri, ci):
        if ci is None:
            return ""
        v = raw.iat[ri, ci]
        return "" if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v).strip()

    def cell(ri, key):
        return cell_at(ri, colmap.get(key))

    def hyperlink(ri, key):
        ci = colmap.get(key)
        if ci is None or ws is None:
            return ""
        try:
            c = ws.cell(row=ri + 1, column=ci + 1)
            if c.hyperlink and c.hyperlink.target:
                return c.hyperlink.target
        except Exception:
            pass
        return ""

    rows = []
    for ri in range(hidx + 1, len(raw)):
        sku = cell(ri, "sku")
        barcode = cell(ri, "barcode")
        title = cell(ri, "title")
        if not sku and not barcode:
            continue  # skip section/category/blank rows
        media = hyperlink(ri, "media") or cell(ri, "media")
        image = hyperlink(ri, "image") or cell(ri, "image")
        if media and not media.startswith("http"):
            media = ""  # text like "Media Link" with no real hyperlink
        if image and not image.startswith("http"):
            image = ""
        rows.append({
            "sku": sku, "title": title, "feature": cell(ri, "feature"),
            "color": cell(ri, "color"), "price": cell_at(ri, price_col),
            "barcode": barcode, "media": media, "image": image,
        })
    # Variant rows (blank title/feature/price) inherit from the parent row above,
    # and share a group_id with it (→ a colour variation family).
    last = {"title": "", "feature": "", "price": ""}
    gid = -1
    for r in rows:
        own = bool(str(r.get("title") or "").strip())
        if own:
            gid += 1
        r["is_child"] = not own
        r["group_id"] = max(gid, 0)
        for k in ("title", "feature", "price"):
            if str(r.get(k) or "").strip():
                last[k] = r[k]
            elif last[k]:
                r[k] = last[k]
    return pd.DataFrame(rows)


def _load_pricelist(up, use_sample: bool) -> pd.DataFrame:
    if up is not None:
        return _parse_pricelist_bytes(up.getvalue(), up.name.lower().endswith(".csv"))
    if use_sample:
        from core import mock_data
        s = mock_data.sample_price_list().copy()
        s["feature"] = ""
        s["color"] = ""
        s["barcode"] = ""
        s["image"] = ""
        s = s.rename(columns={"media_link": "media"})
        return s[["sku", "title", "price", "feature", "color", "barcode", "media", "image"]]
    return pd.DataFrame()


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "")
                         for p in PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return ""


def _load_packaging(files) -> list:
    """Packaging files (PDF / CSV / Excel) → list of (label, text). Matched to
    products later by scanning the text for each SKU/barcode."""
    if not files:
        return []
    if not isinstance(files, list):
        files = [files]
    out = []
    for f in files:
        name = f.name.lower()
        try:
            if name.endswith(".pdf"):
                txt = _pdf_text(f.getvalue())
                if txt.strip():
                    out.append((f.name, txt))
            else:
                df = (pd.read_csv(f, dtype=str) if name.endswith(".csv")
                      else pd.read_excel(f, dtype=str))
                # one text block per row, prefixed with its sku/barcode for matching
                for _, r in df.iterrows():
                    block = " | ".join(f"{c}: {r[c]}" for c in df.columns
                                       if pd.notna(r[c]) and str(r[c]).strip())
                    if block:
                        out.append((f.name, block))
        except Exception:
            continue
    return out


def _packaging_for(sku: str, barcode: str, packaging: list) -> str:
    """Find the packaging file matching this SKU/barcode (by filename or content)."""
    for name, text in packaging:
        hay_name = str(name)
        if (sku and (sku in text or sku in hay_name)) or \
           (barcode and (barcode in text or barcode in hay_name)):
            return text
    # If exactly one packaging file was given, assume it's for the item.
    if len(packaging) == 1:
        return packaging[0][1]
    return ""


def _parse_dimensions(text: str) -> dict:
    """Extract dimensions + weights from packaging text. Handles any separator
    (x, *, ×, or the � that PDFs sometimes decode it to) and converts mm → cm.
    Returns flat keys: item_/package_ length/width/height + units, weights."""
    out = {}
    t = str(text or "")
    # Prefer a "Product Size / Dimensions" line; else 3 numbers ending in a length unit.
    m = re.search(r"(?:product\s*size|size|dimension[s]?)\s*[-:]?\s*"
                  r"([\d.]+)\s*[^\d.\s]{1,3}\s*([\d.]+)\s*[^\d.\s]{1,3}\s*([\d.]+)\s*"
                  r"(mm|cm|millimet\w*|centimet\w*|in\w*|\")?", t, re.I)
    if not m:
        m = re.search(r"([\d.]+)\s*[^\d.\s]{1,3}\s*([\d.]+)\s*[^\d.\s]{1,3}\s*([\d.]+)\s*"
                      r"(mm|cm|millimet\w*|centimet\w*|inch\w*|in)\b", t, re.I)
    if m:
        l, w, h = float(m.group(1)), float(m.group(2)), float(m.group(3))
        u = (m.group(4) or "cm").lower()
        if u.startswith("mm") or u.startswith("millim"):
            l, w, h = round(l / 10, 2), round(w / 10, 2), round(h / 10, 2)
            unit = "centimeters"
        elif u.startswith("in") or u == '"':
            unit = "inches"
        else:
            unit = "centimeters"
        out.update({"item_length": l, "item_width": w, "item_height": h,
                    "dimension_unit": unit, "package_length": l, "package_width": w,
                    "package_height": h, "package_dimension_unit": unit})
    # Weight: 'Net Weight - 382g', 'Gross Weight (KG): 9.6', '0.5 kg'
    wt = re.search(r"(?:net\s*weight|gross\s*weight|weight)\s*[^\d-]*[-:]?\s*"
                   r"([\d.]+)\s*(kg|kgs|kilograms?|g|gram[s]?)?", t, re.I)
    if wt:
        val = float(wt.group(1))
        u = (wt.group(2) or "g").lower()
        unit = "grams" if u.startswith("g") else "kilograms"
        out.update({"package_weight": val, "package_weight_unit": unit,
                    "shipping_weight": val, "shipping_weight_unit": unit})
    return out


# Default warranty/support line for the mandatory "What You Get" last bullet.
_DEFAULT_WARRANTY = ("24-Hour Customer Service, Lifetime Technical Support and "
                     "Free 12 + 12 Months Warranty")


def _listing_copy(draft: dict) -> dict:
    """Generate Amazon copy to the seller's standards:
       • Title  : < 200 chars, brand + type + keyword-rich feature phrases (SEO).
       • Bullets: 5-6, each = Bold Lead-in: 2-3 sentences; LAST = 'What You Get:'.
       • Desc   : keyword-dense paragraph.
    Uses Claude when an Anthropic key is set, else a structured rule-based builder."""
    bd = _brand_defaults()
    brand = draft.get("brand") or bd["brand"] or "Porodo"
    name = draft.get("title", "")
    color = draft.get("extra", {}).get("color", "")
    feats = _clean_feature(draft.get("feature", ""))
    warranty = db.get_setting("default_warranty_line", "") or _DEFAULT_WARRANTY

    key = db.get_setting("anthropic_api_key", "")
    if key and (name or feats):
        try:
            from core import assistant
            system = ("You are an expert Amazon.ae SEO listing copywriter. You write "
                      "keyword-rich, policy-compliant copy that ranks high and reads naturally. "
                      "Return ONLY valid JSON.")
            prompt = (
                f"Brand: {brand}\nProduct: {name}\nColor: {color}\n"
                f"Warranty/Support line (use verbatim in the last bullet): {warranty}\n"
                f"Product features/specs:\n" + "\n".join("- " + f for f in feats) +
                "\n\nWrite an Amazon.ae listing as JSON with keys title, bullets, description, keywords.\n\n"
                "TITLE (string): ONE line, MUST be UNDER 200 characters (aim 185-198). Begin with the "
                "Brand, then the product type, then the most important features/specs as "
                "comma/ampersand-separated keyword phrases — mirror how top-selling Amazon listings "
                "pack searchable keywords buyers actually type, using ONLY terms this product truly has. "
                "Title Case. NO promotional words (best, cheap, sale, #1, free shipping, guarantee).\n\n"
                "BULLETS (array of 5 to 6 strings): order by feature importance. Each non-final bullet = "
                "a Bold Lead-in Phrase, then ': ', then 2-3 complete sentences of benefit-led, simple, "
                "readable copy that still weaves in the important keywords (e.g. "
                "'Powerful 2950W Dual Boiler: <2-3 sentences>'). The FINAL bullet MUST begin with "
                f"'What You Get:' and list the product plus this exact text: '{warranty}'.\n\n"
                "DESCRIPTION (string): a keyword-dense paragraph of 4-6 sentences that repeats and varies "
                "the most important search keywords, specs and use-cases (it aids search even if unread).\n\n"
                "KEYWORDS (string): 12-20 comma-separated backend search terms; do not repeat the brand.\n\n"
                "Return JSON only.")
            txt, status = assistant.complete(system, prompt, max_tokens=1800)
            if status == "ok" and txt and "{" in txt:
                data = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])
                title = str(data.get("title", "")).strip()[:198]
                bullets = [str(b).strip() for b in data.get("bullets", []) if str(b).strip()][:6]
                if bullets and not bullets[-1].lower().startswith("what you get"):
                    bullets.append(f"What You Get: {name} — {warranty}.")
                return {"title": title, "bullets": bullets,
                        "description": str(data.get("description", "")),
                        "keywords": str(data.get("keywords", ""))}
        except Exception:
            pass

    # ---- Structured rule-based fallback (same shape, keyword-packed) ----
    title = name if (brand and brand.lower() in name.lower()) else f"{brand} {name}".strip()
    # Build keyword phrases: prefer descriptive features (skip raw spec labels like
    # "Rated Voltage"), and synthesise a battery keyword from the parsed mAh.
    bat = _parse_battery(draft.get("feature", ""))
    phrases = []
    if bat.get("mah"):
        phrases.append(f"{int(bat['mah'])}mAh Rechargeable Battery")
    spec_label = re.compile(r"rated|voltage|current|charging input|operating|time|capacity|input",
                            re.I)
    for f in feats:
        if ":" in f:
            lead, val = f.split(":", 1)
            val = val.strip()
            # keep a descriptive value (not a pure number/unit), skip spec labels
            if val and not re.match(r"^[\d.\s/vawhmVAWHM%-]+$", val) and len(val) <= 32:
                phrases.append(val)
        elif 2 < len(f) <= 40 and not spec_label.search(f):
            phrases.append(f)
    for e in dict.fromkeys(phrases):
        cand = f"{title}, {e}"
        if len(cand) < 198:
            title = cand
        else:
            break
    if color and color.lower() not in title.lower() and len(title) + len(color) + 4 < 198:
        title = f"{title}, {color}"
    title = title[:198]

    bullets = []
    for f in feats[:5]:
        if ":" in f:
            lead, desc = f.split(":", 1)
            bullets.append(f"{lead.strip()}: {desc.strip()}")
        else:
            bullets.append(f.strip())
    bullets = [b for b in bullets if b] or [f"{name} by {brand}".strip()]
    bullets.append(f"What You Get: {name} — {warranty}.")

    desc_bits = feats[:12] or [name]
    description = (f"{name}. " + " ".join(desc_bits))[:1900]
    words = re.findall(r"[A-Za-z]{4,}", " ".join([name] + feats[:10]))
    keywords = ", ".join(list(dict.fromkeys(w.lower() for w in words))[:18]) if words else ""
    return {"title": title, "bullets": bullets, "description": description, "keywords": keywords}


def _common_prefix(skus: list) -> str:
    if not skus:
        return "PARENT"
    p = str(skus[0])
    for s in skus[1:]:
        s = str(s)
        while p and not s.startswith(p):
            p = p[:-1]
    return (p.rstrip("-_ ") or str(skus[0]))[:30]


def _build_feed_items(ready: list) -> tuple:
    """Turn ready 'prepared' items into feed items, grouping colour variants into
    parent+child variation families. Returns (items, family_count)."""
    from collections import defaultdict
    groups = defaultdict(list)
    for p in ready:
        groups[p["draft"].get("group_id", p["sku"])].append(p)
    items, families = [], 0
    for members in groups.values():
        if len(members) == 1:
            p = members[0]
            items.append({"sku": p["sku"], "product_type": p["pt"], "attributes": p["attrs"]})
            continue
        families += 1
        base = members[0]
        parent_sku = _common_prefix([m["sku"] for m in members]) + "-PARENT"
        shared = {k: base["attrs"].get(k) for k in
                  ("item_name", "brand", "manufacturer", "bullet_point", "product_description")
                  if base["attrs"].get(k)}
        parent_flat = dict(shared)
        parent_flat["parentage_level"] = "parent"
        parent_flat["variation_theme"] = "COLOR_NAME"
        items.append({"sku": parent_sku, "product_type": base["pt"], "attributes": parent_flat})
        for m in members:
            child = dict(m["attrs"])
            child["parentage_level"] = "child"
            child["child_relationship_type"] = "variation"
            child["variation_theme"] = "COLOR_NAME"
            child["color_name"] = m["draft"].get("color", "") or child.get("color", "")
            items.append({"sku": m["sku"], "product_type": m["pt"], "attributes": child})
    return items, families


def _fetch_drafts() -> list[dict]:
    """Mode A (price list — primary) / Mode B (URL) → list of draft dicts."""
    mode = st.radio("Input mode", ["📄 Price List (recommended for new arrivals)",
                                   "🔗 Paste URL(s)"], horizontal=True)
    drafts: list[dict] = []
    if mode.startswith("📄"):
        st.caption("Upload your price list (any layout — headers can be lower in the sheet, "
                   "section rows are skipped). RRP is used as the price; the Feature column "
                   "becomes the title/bullets/description; barcodes apply your 0/last-digit rule; "
                   "media hyperlinks are read automatically.")
        up = st.file_uploader("Price list (CSV/Excel)", type=["csv", "xlsx"], key="aic_pricelist")
        pack = st.file_uploader(
            "Packaging files (PDF / CSV / Excel) — dimensions & weights (optional, multiple)",
            type=["pdf", "csv", "xlsx"], accept_multiple_files=True, key="aic_packaging")
        use_sample = st.checkbox("Use sample price list", value=not bool(up))
        # Cache by upload identity so images are fetched ONCE per file (not every rerun).
        sig = ((up.name, up.size) if up else ("sample", use_sample),
               tuple((f.name, f.size) for f in (pack or [])))
        if (up or use_sample) and st.session_state.get("aic_sig") == sig \
                and st.session_state.get("aic_drafts"):
            return st.session_state["aic_drafts"]
        if up or use_sample:
            with st.spinner("Reading price list and fetching product images…"):
                df = _load_pricelist(up, use_sample)
                packaging = _load_packaging(pack)
                for _, r in df.iterrows():
                    sku = str(r.get("sku") or "").strip()
                    feature = str(r.get("feature") or "")
                    # Match a packaging file (by SKU/barcode in its text) → enrich + dims.
                    bc_raw = str(r.get("barcode") or "").strip()
                    pack_text = _packaging_for(sku, bc_raw, packaging)
                    pack_dims = _parse_dimensions(pack_text) if pack_text else {}
                    if pack_text:
                        feature = feature + "\n" + pack_text[:1500]
                    media = str(r.get("media") or "")
                    res = (oskar_source.fetch_images_from_media_link(media, sku)
                           if (media or sku) else {"images": [], "ok": False})
                    if not res["images"] and str(r.get("image") or "").startswith("http"):
                        res = {"images": [r["image"]], "ok": True}
                    extra = {}
                    if str(r.get("color") or "").strip():
                        extra["color"] = r["color"]
                    if bc_raw:
                        bc = _normalize_barcode(bc_raw)
                        extra["external_product_id"] = bc
                        extra["external_product_id_type"] = "UPC" if len(bc) == 12 else "EAN"
                    # Auto-extract battery energy (Wh) from the feature specs.
                    bat = _parse_battery(feature)
                    if bat.get("lithium_energy"):
                        extra["lithium_energy"] = bat["lithium_energy"]
                    # Dimensions & weights from the matched packaging file.
                    extra.update(pack_dims)
                    drafts.append({"sku": sku, "title": str(r.get("title") or ""),
                                   "price": r.get("price"), "images": res["images"],
                                   "img_ok": res["ok"], "brand": "", "feature": feature,
                                   "extra": extra,
                                   "group_id": r.get("group_id", 0),
                                   "is_child": bool(r.get("is_child", False)),
                                   "color": str(r.get("color") or "")})
            st.caption(f"Parsed {len(drafts)} product(s); images fetched from connect.oskarme.com.")
        st.session_state["aic_drafts"] = drafts
        st.session_state["aic_sig"] = sig
    else:
        st.caption("Paste one item URL per line — the scraper reads Open Graph / JSON-LD / "
                   "common selectors for title, price, brand, description and images.")
        urls = st.text_area("Item URL(s)", placeholder="https://www.example.com/product/123",
                            height=90)
        if st.button("🔎 Fetch from URL(s)") and urls.strip():
            got = []
            for url in [u.strip() for u in urls.splitlines() if u.strip()]:
                res = oskar_source.scrape_product_from_url(url)
                got.append({"sku": "", "title": res.get("title", ""),
                            "price": res.get("price"), "images": res.get("images", []),
                            "img_ok": bool(res.get("images")), "brand": res.get("brand", ""),
                            "source_url": url, "extra": {}})
            st.session_state["aic_drafts"] = got
    return st.session_state.get("aic_drafts", drafts)


def _auto_attributes(draft: dict, reqs: list, opt: dict) -> dict:
    """Build the full attribute dict from price-list data + defaults (no user input)."""
    return {f["name"]: _prefill(f, draft, opt) for f in reqs}


def _push_one(sku: str, pt: str, attributes: dict, images: list, use_mock: bool) -> dict:
    """Submit one listing and persist on success. Returns the API response."""
    res = client().push_listing({"sku": sku, "product_type": pt, "attributes": attributes})
    if res.get("status") in ("mock_ok", "ok", "submitted"):
        db.upsert_catalog_item(sku=sku, asin=res.get("asin", ""),
                               title=attributes.get("item_name", ""),
                               brand=attributes.get("brand", ""), category=pt, status="listed")
        db.add_ready_to_list(sku, attributes.get("item_name", ""),
                             float(attributes.get("standard_price") or 0), images,
                             {"product_type": pt, "attributes": attributes})
        db.add_task(f"Verify Amazon listing live: {attributes.get('item_name','')}",
                    f"Pushed via SP-API (SKU {sku}).",
                    module="Inventory & Listing Intake", priority="medium", related_id=sku)
    return res


def _auto_creation_tab() -> None:
    st.markdown(section_label("🤖 Auto Item Creation → Amazon"), unsafe_allow_html=True)
    st.markdown(
        "<p style='color:var(--muted); font-size:.85rem; margin-top:-4px'>"
        "Upload your price list of new arrivals → the dashboard auto-fills <b>Amazon's required "
        "fields</b> per item and pushes the complete ones to Amazon via SP-API in one batch.</p>",
        unsafe_allow_html=True)

    use_mock = db.get_setting("use_mock_amazon", "1") == "1"
    bd = _brand_defaults()
    st.markdown(
        badge("Mock Amazon — add SP-API keys in Settings to push for real" if use_mock
              else "Live SP-API", "amber" if use_mock else "green") + " " +
        (badge(f"Brand owner: {bd['brand'] or '(set brand in Settings)'} · GTIN-exempt", "blue")
         if bd["brand_owner"] else ""),
        unsafe_allow_html=True)

    drafts = _fetch_drafts()
    if not drafts:
        return
    drafts = [_apply_defaults(d) for d in drafts]

    # Per-render requirements cache (avoids duplicate live API calls per product type).
    req_cache: dict = {}

    live_mode = db.get_setting("use_mock_amazon", "1") != "1"

    def _reqs(pt: str) -> list:
        if pt not in req_cache:
            try:
                if live_mode:
                    # CORE (auto-filled) + Amazon's extra required + discovered fields.
                    req_cache[pt] = _relax_for_brand_owner(_hybrid_requirements(pt))
                else:
                    req_cache[pt] = _relax_for_brand_owner(client().get_listing_requirements(pt))
            except Exception:
                req_cache[pt] = _relax_for_brand_owner(_core_fields()) if live_mode else []
        return req_cache[pt]

    # ---- BATCH overview --------------------------------------------------
    st.markdown(section_label("1 · Batch — validate all items"), unsafe_allow_html=True)
    prepared = []
    rows = []
    for i, d in enumerate(drafts):
        pt = _guess_product_type(d.get("title", ""))
        opt = _listing_copy(d)
        reqs = _reqs(pt)
        sku = d.get("sku") or _slug(d.get("title", ""))
        if not reqs:
            # Couldn't resolve Amazon's fields for the guessed type — fix in editor.
            prepared.append({"i": i, "draft": d, "pt": pt, "reqs": [], "attrs": {},
                             "sku": sku, "missing": ["set product type"], "opt": opt})
            rows.append({"SKU": sku, "Title": (d.get("title") or "")[:42], "Type": pt,
                         "Price": "—", "Status": "set product type"})
            continue
        attrs = _auto_attributes(d, reqs, opt)
        missing = [f["label"] for f in reqs
                   if f.get("required") and not str(attrs[f["name"]]).strip()]
        prepared.append({"i": i, "draft": d, "pt": pt, "reqs": reqs, "attrs": attrs,
                         "sku": sku, "missing": missing, "opt": opt})
        rows.append({"SKU": sku, "Title": (d.get("title") or "")[:42], "Type": pt,
                     "Price": f"AED {float(attrs.get('standard_price') or 0):,.0f}",
                     "Status": "Ready" if not missing else f"{len(missing)} missing"})

    styled_table(pd.DataFrame(rows), highlight={
        "row-good": lambda r: r["Status"] == "Ready",
        "row-warn": lambda r: r["Status"] != "Ready"},
        badge_cols={"Status": {"Ready": ("✓ Ready", "green")}})

    ready_items = [p for p in prepared if not p["missing"]]
    # Detect colour-variation families among the items.
    from collections import Counter
    gcounts = Counter(p["draft"].get("group_id", p["sku"]) for p in prepared)
    fam_count = sum(1 for n in gcounts.values() if n > 1)
    if fam_count:
        st.caption(f"🎨 {fam_count} colour-variation family(ies) detected — these will be "
                   f"created as a parent listing with colour children.")
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(badge(f"{len(ready_items)}/{len(prepared)} ready to push",
                          "green" if ready_items else "amber"), unsafe_allow_html=True)
    with c2:
        if st.button(f"🚀 Push ALL {len(ready_items)} ready items to Amazon",
                     use_container_width=True, type="primary", disabled=not ready_items):
            # Build ONE JSON_LISTINGS_FEED, grouping colour variants into families.
            items, fam_n = _build_feed_items(ready_items)
            with st.spinner(f"Submitting JSON_LISTINGS_FEED "
                            f"({len(items)} messages, {fam_n} variation families)…"):
                res = client().push_listings_feed(items)
            per = res.get("per_sku", {})
            # persist accepted/submitted ones locally
            for p in ready_items:
                info = per.get(p["sku"], {})
                if info.get("status") in ("accepted", "submitted"):
                    db.upsert_catalog_item(sku=p["sku"], title=p["attrs"].get("item_name", ""),
                                           brand=p["attrs"].get("brand", ""), category=p["pt"],
                                           status="listed")
                    db.add_ready_to_list(p["sku"], p["attrs"].get("item_name", ""),
                                         float(p["attrs"].get("standard_price") or 0),
                                         p["draft"].get("images", []),
                                         {"product_type": p["pt"], "attributes": p["attrs"]})
            sub = res.get("submitted", 0)
            st.success(f"Feed {res.get('feedId','—')} · status {res.get('processingStatus','—')} "
                       f"· accepted {res.get('accepted',0)} / rejected {res.get('rejected',0)}"
                       + (f" / still-processing {sub}" if sub else "")
                       + f" ({'mock' if use_mock else 'LIVE'}).")
            if sub:
                st.info("Some items are still processing on Amazon — check Seller Central "
                        "in a few minutes; not confirmed yet.")
            rejected = {s: i["issues"] for s, i in per.items() if i.get("status") == "rejected"}
            if rejected:
                st.warning("Rejected items:\n" +
                           "\n".join(f"• {s}: {'; '.join(iss) or 'see report'}"
                                     for s, iss in rejected.items()))
    if len(ready_items) < len(prepared):
        st.caption("Items with missing fields → complete them in the detailed editor below.")

    # ---- DETAILED editor (complete / fix one item) ----------------------
    st.markdown(section_label("2 · Detailed editor — complete or fix one item"),
                unsafe_allow_html=True)
    with st.expander("✏️ Open detailed editor", expanded=bool(len(ready_items) < len(prepared))):
        labels = [f"{p['i']+1}. {p['draft'].get('title') or '(untitled)'} "
                  f"({'ready' if not p['missing'] else str(len(p['missing']))+' missing'})"
                  for p in prepared]
        sel = st.selectbox("Item", range(len(prepared)), format_func=lambda i: labels[i],
                           key="aic_pick")
        p = prepared[sel]
        draft, pt0 = p["draft"], p["pt"]
        types = client().get_product_types()
        pt = st.selectbox("Amazon product type", types,
                          index=types.index(pt0) if pt0 in types else 0, key="aic_pt")
        reqs = _reqs(pt)
        if not reqs:
            st.warning("Couldn't load Amazon's required fields for this product type. "
                       "Pick a different product type above (the list comes from your live "
                       "Amazon marketplace).")
        opt = _listing_copy(draft)
        draft_id = _slug(draft.get("sku") or draft.get("title") or str(sel))

        if draft.get("images"):
            st.image(draft["images"][0], width=130, caption="Fetched image")

        seller_sku = st.text_input("Seller SKU *",
                                   value=draft.get("sku") or _slug(draft.get("title", "")),
                                   key=f"aic_sku_{draft_id}")
        attributes = {}
        cols = st.columns(2)
        for k, f in enumerate(reqs):
            key = f"aicf_{draft_id}_{f['name']}"
            prefill = _prefill(f, draft, opt)
            label = f["label"] + (" *" if f.get("required") else "")
            with cols[k % 2]:
                if f["type"] == "select":
                    opts = f["options"] or [""]
                    default = prefill if prefill in opts else f.get("default", opts[0])
                    val = st.selectbox(label, opts,
                                       index=opts.index(default) if default in opts else 0, key=key)
                elif f["type"] == "number":
                    val = st.number_input(label, value=float(prefill or f.get("default", 0) or 0),
                                          key=key)
                elif f["type"] == "textarea":
                    val = st.text_area(label, value=str(prefill or ""), height=90, key=key)
                else:
                    val = st.text_input(label, value=str(prefill or ""), key=key)
            attributes[f["name"]] = val

        missing = [f["label"] for f in reqs
                   if f.get("required") and not str(attributes[f["name"]]).strip()]
        if not reqs:
            missing = ["Select a valid product type"] + missing
        if not seller_sku.strip():
            missing = ["Seller SKU"] + missing
        total = sum(1 for f in reqs if f.get("required")) + 1
        st.markdown(badge(f"{total - len(missing)}/{total} required complete",
                          "green" if not missing else "amber"), unsafe_allow_html=True)
        if missing:
            st.markdown(alert("Still required: " + ", ".join(missing), kind="amber", icon="✏️"),
                        unsafe_allow_html=True)

        # Catalog check + validation preview (per the SP-API listing flow).
        ce1, ce2 = st.columns(2)
        with ce1:
            if st.button("🔎 Check if ASIN exists", key=f"aic_cat_{draft_id}"):
                bc = str(attributes.get("external_product_id", "")).strip()
                if bc:
                    items = client().search_catalog_items(
                        bc, attributes.get("external_product_id_type", "EAN"))
                    if items:
                        st.info("Existing match(es): " +
                                ", ".join(i.get("asin", "?") for i in items[:5]) +
                                " — consider listing as an offer on the existing ASIN.")
                    else:
                        st.success("No existing ASIN — this will create a new product.")
                else:
                    st.caption("No barcode to search the catalog.")
        with ce2:
            if st.button("✅ Validate (preview, no commit)", key=f"aic_val_{draft_id}"):
                v = client().validate_preview(seller_sku.strip() or "PREVIEW", pt, attributes)
                if v.get("ok"):
                    st.success(f"✅ Valid ({v.get('status')}) — ready to push to Amazon.")
                else:
                    # Auto-discover any required fields Amazon flagged and add them to the form.
                    flagged = set()
                    for i in v.get("issues", []) + v.get("errors", []):
                        if isinstance(i, dict) and i.get("severity", "ERROR") == "ERROR":
                            for an in (i.get("attributeNames") or []):
                                flagged.add(an)
                    known = {f["name"] for f in reqs}
                    nested_parents = {p for p, subs in _NESTED_FIELDS.items()
                                      if any(s["name"] in known for s in subs)}
                    new = [a for a in flagged if a not in known and a not in nested_parents
                           and a not in _CORE_COVERED]
                    if new:
                        store = st.session_state.setdefault("aic_more", {}).setdefault(pt, set())
                        store.update(new)
                        req_cache.pop(pt, None)  # rebuild form with the new fields
                        st.warning("Amazon needs more fields: " +
                                   ", ".join(a.replace('_', ' ') for a in new) +
                                   ". I've added them below — fill any blanks and validate again.")
                        st.rerun()
                    else:
                        errs = v.get("errors", []) or v.get("issues", [])
                        msg = "\n".join("• " + (e.get("message", "") if isinstance(e, dict) else str(e))
                                        for e in errs[:10])
                        st.error(("Validation issues:\n" + msg) if msg else f"Invalid: {v.get('status')}")

        if st.button("🚀 Push this item to Amazon (Feeds API)", use_container_width=True,
                     type="primary", disabled=bool(missing)):
            res = _push_one(seller_sku.strip(), pt, attributes, draft.get("images", []), use_mock)
            status = res.get("status")
            fid = res.get("feedId", "—")
            if status in ("mock_ok", "ok"):
                st.success(f"✅ ACCEPTED by Amazon — feed {fid} processed (DONE). "
                           f"SKU {seller_sku.strip()}. The listing will appear in Seller Central shortly.")
                st.balloons()
            elif status == "submitted":
                st.info(f"📤 SUBMITTED — feed {fid} (status: {res.get('processingStatus')}). "
                        f"Amazon is still processing it. It's NOT confirmed yet — check Seller "
                        f"Central → Inventory in a few minutes, or re-validate the SKU later.")
            elif status == "invalid":
                st.error("Missing required fields: " + ", ".join(res.get("missing", [])))
            else:
                # Auto-discover any fields Amazon's feed report flagged, add to the form.
                report = (res.get("raw") or {}).get("report") or {}
                flagged = set()
                for i in report.get("issues", []):
                    if i.get("severity") == "ERROR":
                        for an in (i.get("attributeNames") or []):
                            flagged.add(an)
                known = {f["name"] for f in reqs}
                nested_parents = {p for p, subs in _NESTED_FIELDS.items()
                                  if any(s["name"] in known for s in subs)}
                new = [a for a in flagged if a not in known and a not in nested_parents
                       and a not in _CORE_COVERED]
                issues = res.get("issues") or []
                if new:
                    st.session_state.setdefault("aic_more", {}).setdefault(pt, set()).update(new)
                    req_cache.pop(pt, None)
                    st.warning("❌ Amazon rejected — and asked for more fields: " +
                               ", ".join(a.replace('_', ' ') for a in new) +
                               ". Added below — fill any blanks and push again.")
                    st.rerun()
                else:
                    st.error("❌ REJECTED by Amazon:\n" +
                             ("\n".join("• " + str(i) for i in issues) if issues else str(res)))

    # ---- submitted / ready queue ----------------------------------------
    st.markdown(section_label("📦 Submitted / Ready-to-List"), unsafe_allow_html=True)
    ready = db.get_ready_to_list()
    if ready:
        qdf = pd.DataFrame([{"SKU": r["sku"], "Title": r["title"],
                             "Price": f"AED {r['price']:,.0f}",
                             "Type": (r["payload"].get("product_type", "—")
                                      if isinstance(r["payload"], dict) else "—")}
                            for r in ready])
        styled_table(qdf, highlight={"row-good": lambda r: True})
        export_buttons(qdf, "ready_to_list")
    else:
        st.caption("Nothing pushed yet.")


def render(nav=None) -> None:
    page_header("Inventory & Listing Intake",
                "Classify arrivals, plan restocks, and auto-create listings", icon="📥")
    t1, t2, t3 = st.tabs(["✨ New Arrivals", "🚚 Restock Pending", "🤖 Auto Item Creation"])
    with t1:
        _new_arrivals_tab()
    with t2:
        _restock_tab()
    with t3:
        _auto_creation_tab()
```

================================================================
FILE: modules/optimization.py
================================================================
```python
"""
modules/optimization.py
=======================
🪄 Listing Optimization (Module 3).

For a chosen item it: pulls top best-sellers in the same Amazon category (via
api_client; mock now), extracts their keywords, then generates an optimized
Title / Bullets / Keywords / Description that respects Amazon policy (length, no
promo claims). Output is shown in copyable code blocks with Export.

optimize_item() is the reusable entry the Intake module also calls. Generation is
routed through assistant.answer() when an Anthropic key is set, else a
deterministic rule-based builder (mock_data.optimized_listing).
"""

from __future__ import annotations
import re
import pandas as pd
import streamlit as st

from core import db, mock_data
from core.api_client import client
from core.components import styled_table, export_buttons, page_header
from core.styles import section_label, badge

TITLE_LIMIT = 200
# Words Amazon disallows in titles (promotional claims).
_BANNED = ["best", "cheap", "sale", "free shipping", "guarantee", "100%", "#1", "hot"]


def _policy_clean_title(title: str) -> tuple[str, list[str]]:
    """Strip banned promo terms and enforce length. Returns (clean, removed)."""
    removed = []
    clean = title
    for w in _BANNED:
        if re.search(rf"\b{re.escape(w)}\b", clean, flags=re.IGNORECASE):
            removed.append(w)
            clean = re.sub(rf"\b{re.escape(w)}\b", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s{2,}", " ", clean).strip(" -|")
    return clean[:TITLE_LIMIT], removed


def optimize_item(title_seed: str, category: str, extra_keywords: str = "") -> dict:
    """Reusable optimizer. Pulls category keywords then builds the listing."""
    top = client().get_top_sellers_in_category(category)
    mined = " ".join(top["keywords"].tolist()) if not top.empty else ""
    keywords = (extra_keywords + " " + mined).strip()
    listing = mock_data.optimized_listing(title_seed, category, keywords)
    listing["title"], _ = _policy_clean_title(listing["title"])
    return listing


def render(nav=None) -> None:
    page_header("Listing Optimization",
                "Policy-safe titles, bullets, keywords & descriptions from category data",
                icon="🪄")

    listings = client().get_my_listings()
    src = st.radio("Optimize for", ["An existing listing", "Custom item"], horizontal=True)

    if src == "An existing listing":
        pick = st.selectbox("Item", listings["title"].tolist())
        row = listings[listings["title"] == pick].iloc[0]
        title_seed, category = row["title"], row["category"]
    else:
        title_seed = st.text_input("Product name", "Marshall Emberton III - Black")
        category = st.selectbox("Category", ["Audio", "Charging", "Smart Home", "Phones", "Home"])

    extra = st.text_input("Extra keywords (optional)", "")

    # Show the best-sellers we mine keywords from.
    with st.expander("🔍 Category best-sellers (keyword source)", expanded=False):
        top = client().get_top_sellers_in_category(category)
        styled_table(top)

    if st.button("⚡ Generate Optimized Listing", use_container_width=True):
        listing = optimize_item(title_seed, category, extra)
        st.session_state["last_optimized"] = listing

    listing = st.session_state.get("last_optimized")
    if not listing:
        return

    title_len = len(listing["title"])
    ok = title_len <= TITLE_LIMIT
    len_badge = badge(f"{title_len}/{TITLE_LIMIT} chars", "green" if ok else "coral")
    st.markdown(section_label("Optimized Title") + " " + len_badge, unsafe_allow_html=True)
    st.code(listing["title"], language="text")

    st.markdown(section_label("Bullet Points"), unsafe_allow_html=True)
    st.code("\n".join(f"• {b}" for b in listing["bullets"]), language="text")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(section_label("Backend Keywords"), unsafe_allow_html=True)
        st.code(listing["keywords"], language="text")
    with c2:
        st.markdown(section_label("Description"), unsafe_allow_html=True)
        st.code(listing["description"], language="text")

    # Export the optimized listing.
    out = pd.DataFrame([{
        "title": listing["title"], "bullets": " | ".join(listing["bullets"]),
        "keywords": listing["keywords"], "description": listing["description"],
    }])
    export_buttons(out, "optimized_listing")

    if st.button("➕ Save as task"):
        db.add_task(f"Apply optimized copy: {title_seed}",
                    "Generated in Listing Optimization.",
                    module="Listing Optimization", priority="low")
        st.success("Task added.")
```

================================================================
FILE: modules/stock.py
================================================================
```python
"""
modules/stock.py
================
📦 Stock Management (Module 4).

  * Upload TWO files: Amazon inventory + Warehouse inventory.
  * Match items across both (SKU/ASIN/barcode, with fuzzy title fallback).
  * Apply per-brand / per-category min-stock rules from Stock Configuration.
  * Output: Out-of-Stock / below-threshold list (table + Export) and fire
    notifications for out-of-stock items.

Sub-tab "Stock Configuration" persists thresholds to the DB.
"""

from __future__ import annotations
import pandas as pd
import streamlit as st

from core import db, notifier
from core.util import get_field, fuzzy_match_key
from core.components import styled_table, export_buttons, page_header
from core.styles import section_label, badge, alert


def _normalize(df: pd.DataFrame, qty_default=0) -> pd.DataFrame:
    return pd.DataFrame({
        "sku": get_field(df, "sku", "").astype(str),
        "asin": get_field(df, "asin", "").astype(str),
        "barcode": get_field(df, "barcode", "").astype(str),
        "title": get_field(df, "title", "").astype(str),
        "brand": get_field(df, "brand", "").astype(str),
        "category": get_field(df, "category", "").astype(str),
        "qty": pd.to_numeric(get_field(df, "qty", qty_default), errors="coerce").fillna(0),
    })


def _match(amazon: pd.DataFrame, warehouse: pd.DataFrame) -> pd.DataFrame:
    """Match Amazon rows to warehouse rows by SKU→ASIN→barcode→fuzzy title."""
    overrides = db.get_channel_overrides()  # FBA/FBM decisions from Hazmat
    wh_by_sku = {r["sku"]: r for _, r in warehouse.iterrows() if r["sku"]}
    wh_by_asin = {r["asin"]: r for _, r in warehouse.iterrows() if r["asin"]}
    wh_by_bc = {r["barcode"]: r for _, r in warehouse.iterrows() if r["barcode"]}
    wh_titles = warehouse["title"].tolist()

    rows = []
    for _, a in amazon.iterrows():
        match = None
        if a["sku"] in wh_by_sku:
            match = wh_by_sku[a["sku"]]
        elif a["asin"] in wh_by_asin:
            match = wh_by_asin[a["asin"]]
        elif a["barcode"] in wh_by_bc:
            match = wh_by_bc[a["barcode"]]
        else:
            ft = fuzzy_match_key(a["title"], wh_titles)
            if ft is not None:
                match = warehouse[warehouse["title"] == ft].iloc[0]

        wh_qty = int(match["qty"]) if match is not None else 0
        brand = a["brand"] or (match["brand"] if match is not None else "")
        category = a["category"] or (match["category"] if match is not None else "")
        threshold = db.stock_threshold_for(brand, category)
        rows.append({
            "sku": a["sku"], "title": a["title"], "brand": brand, "category": category,
            "channel": overrides.get(a["sku"], "FBA"),
            "amazon_qty": int(a["qty"]), "warehouse_qty": wh_qty,
            "threshold": threshold,
            "status": "OUT OF STOCK" if a["qty"] == 0 else
                      ("LOW" if a["qty"] < threshold else "OK"),
        })
    return pd.DataFrame(rows)


def _match_tab() -> None:
    c1, c2 = st.columns(2)
    with c1:
        amz_file = st.file_uploader("Amazon inventory file (CSV/Excel)",
                                    type=["csv", "xlsx"], key="stk_amz")
    with c2:
        wh_file = st.file_uploader("Warehouse inventory file (CSV/Excel)",
                                   type=["csv", "xlsx"], key="stk_wh")

    if amz_file:
        amazon = pd.read_csv(amz_file) if amz_file.name.endswith(".csv") else pd.read_excel(amz_file)
    else:
        from core.api_client import client
        amazon = client().get_my_listings().rename(columns={"fba_stock": "qty"})
    if wh_file:
        warehouse = pd.read_csv(wh_file) if wh_file.name.endswith(".csv") else pd.read_excel(wh_file)
    else:
        from core import mock_data
        warehouse = mock_data.inventory_website_items().rename(columns={"warehouse_qty": "qty"})

    src = "uploaded files" if (amz_file and wh_file) else "sample data (upload to override)"
    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)

    matched = _match(_normalize(amazon), _normalize(warehouse))
    oos = matched[matched["status"] != "OK"]

    st.markdown(section_label("Out-of-Stock & Low-Stock Items"), unsafe_allow_html=True)
    if oos.empty:
        st.markdown(alert("All matched items are above threshold.", kind="green", icon="✅"),
                    unsafe_allow_html=True)
    else:
        styled_table(oos, highlight={
            "row-danger": lambda r: r["status"] == "OUT OF STOCK",
            "row-warn": lambda r: r["status"] == "LOW"},
            badge_cols={"status": {"OUT OF STOCK": ("OUT OF STOCK", "coral"),
                                   "LOW": ("LOW", "amber")},
                        "channel": {"FBA": ("FBA", "blue"), "FBM": ("FBM", "violet")}})
        export_buttons(oos, "out_of_stock")

        cta = st.columns([1, 1, 2])
        with cta[0]:
            if st.button("➕ Add to Tasks"):
                for _, r in oos.iterrows():
                    db.add_task(f"Restock: {r['title']} ({r['status']})",
                                f"Amazon {r['amazon_qty']} vs threshold {r['threshold']}; "
                                f"warehouse has {r['warehouse_qty']}.",
                                module="Stock Management",
                                priority="high" if r["status"] == "OUT OF STOCK" else "medium",
                                related_id=r["sku"])
                st.success("Tasks added.")
        with cta[1]:
            if st.button("🔔 Notify"):
                names = ", ".join(oos[oos["status"] == "OUT OF STOCK"]["title"].tolist())
                res = notifier.notify_event("out_of_stock", "Out of stock alert",
                                            f"Out of stock: {names or 'none'}")
                for ch, ok, msg in res:
                    (st.success if ok else st.warning)(f"{ch}: {msg}")


def _config_tab() -> None:
    st.markdown(section_label("Stock Configuration — min thresholds"), unsafe_allow_html=True)
    st.caption("Brand rule overrides category rule, which overrides the global default (10).")

    c1, c2, c3, c4 = st.columns([1.2, 2, 1, 1])
    scope = c1.selectbox("Scope", ["brand", "category"])
    value = c2.text_input("Value (e.g. Apple / Audio)")
    minv = c3.number_input("Min stock", min_value=0, value=15)
    with c4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("💾 Save rule", use_container_width=True) and value:
            db.set_stock_rule(scope, value, int(minv))
            st.success(f"Saved {scope} rule: {value} ≥ {minv}")
            st.rerun()

    rules = db.get_stock_rules()
    if rules:
        styled_table(pd.DataFrame(rules)[["scope_type", "scope_value", "min_stock"]])
    else:
        st.caption("No custom rules yet — global default of 10 applies.")


def render(nav=None) -> None:
    page_header("Stock Management",
                "Match Amazon vs warehouse and surface every stock-out", icon="📦")
    t1, t2 = st.tabs(["🔍 Match & Out-of-Stock", "⚙️ Stock Configuration"])
    with t1:
        _match_tab()
    with t2:
        _config_tab()
```

================================================================
FILE: modules/pricing.py
================================================================
```python
"""
modules/pricing.py
==================
💰 Pricing (Module 5).

Tabs:
  1. Calculator   — manual fee components → min price + price at target profit %.
                    (api_client.get_fees_estimate stub to auto-pull fees later.)
  2. Lost Buybox  — items that lost the buybox on price (api_client; mock), Export,
                    notify.
  3. Market Tracker — set a competitive price for an item. Manual mode (paste your
                    URL + competitor URLs) or Auto mode (suggest best price from
                    feature potential). Fetches Noon/other UAE prices, stores price
                    history in DB, charts it.
"""

from __future__ import annotations
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import db, notifier, mock_data
from core.api_client import client
from core.components import styled_table, export_buttons, page_header
from core.styles import section_label, glow_block, badge, alert, PALETTE


def _calculator() -> None:
    st.markdown(section_label("🧮 Pricing Calculator"), unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        cost = st.number_input("Product cost (AED)", 0.0, value=180.0, step=5.0)
        referral_pct = st.slider("Referral fee %", 5, 20, 15)
    with c2:
        fba = st.number_input("FBA fee (AED)", 0.0, value=14.0, step=1.0)
        shipping = st.number_input("Inbound shipping (AED)", 0.0, value=6.0, step=1.0)
    with c3:
        vat_pct = st.slider("VAT %", 0, 10, 5)
        target_profit = st.slider("Target profit %", 5, 60, 25)

    # Min price: covers cost+fba+shipping+referral+vat with zero profit.
    # P*(1 - referral - vat) = cost+fba+shipping  →  P_min
    denom_min = 1 - referral_pct / 100 - vat_pct / 100
    denom_tgt = 1 - referral_pct / 100 - vat_pct / 100 - target_profit / 100

    fixed = cost + fba + shipping
    if denom_min <= 0 or denom_tgt <= 0:
        st.markdown(alert("Fee percentages too high — no feasible price.", kind="coral",
                          icon="⛔"), unsafe_allow_html=True)
        return
    min_price = fixed / denom_min
    target_price = fixed / denom_tgt

    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown(glow_block(f"AED {min_price:,.2f}", "Minimum Price (break-even)"),
                    unsafe_allow_html=True)
    with cc2:
        st.markdown(glow_block(f"AED {target_price:,.2f}", f"Price @ {target_profit}% profit"),
                    unsafe_allow_html=True)
    st.caption("TODO(api_client.get_fees_estimate): auto-pull referral & FBA fees by ASIN.")


def _lost_buybox() -> None:
    st.markdown(section_label("🏷️ Lost Buybox"), unsafe_allow_html=True)
    df = client().get_lost_buybox()
    df = df.copy()
    df["gap"] = (df["your_price"] - df["buybox_price"]).round(2)
    styled_table(df, highlight={"row-danger": lambda r: True})
    export_buttons(df, "lost_buybox")
    cols = st.columns([1, 1, 2])
    with cols[0]:
        if st.button("➕ Add to Tasks", key="lb_task"):
            for _, r in df.iterrows():
                db.add_task(f"Recover buybox: {r['title']}",
                            f"Competitor at AED {r['buybox_price']} vs your AED {r['your_price']}.",
                            module="Pricing", priority="high", related_id=r["sku"])
            st.success("Tasks added.")
    with cols[1]:
        if st.button("🔔 Notify", key="lb_notify"):
            res = notifier.notify_event("lost_buybox", "Lost buybox alert",
                                        f"{len(df)} items lost the buybox on price.")
            for ch, ok, msg in res:
                (st.success if ok else st.warning)(f"{ch}: {msg}")


def _market_tracker() -> None:
    st.markdown(section_label("🛰️ Market Tracker"), unsafe_allow_html=True)
    listings = client().get_my_listings()
    item = st.selectbox("Item", listings["title"].tolist())
    mode = st.radio("Mode", ["Manual (paste URLs)", "Auto (suggest best price)"],
                    horizontal=True)

    if mode.startswith("Manual"):
        st.text_input("Your item URL", placeholder="https://www.amazon.ae/dp/...")
        st.text_area("Competitor URLs (Amazon / Noon / other UAE, one per line)",
                     placeholder="https://www.noon.com/...\nhttps://www.sharafdg.com/...",
                     height=90)

    if st.button("📡 Fetch competitor prices"):
        comp = mock_data.competitor_prices(item)
        # Persist a price-history snapshot for each source.
        for _, r in comp.iterrows():
            db.add_price(item_id=item, item_name=item, source=r["source"], price=r["price"])
        st.session_state["last_comp"] = comp.to_dict("records")

    comp = st.session_state.get("last_comp")
    if comp:
        cdf = pd.DataFrame(comp)
        lowest = cdf["price"].min()
        your_price = float(listings[listings["title"] == item]["price"].iloc[0])
        st.markdown(badge(f"Lowest market: AED {lowest:,.0f}", "amber") + " " +
                    badge(f"Your price: AED {your_price:,.0f}",
                          "coral" if your_price > lowest else "green"),
                    unsafe_allow_html=True)
        styled_table(cdf, highlight={"row-good": lambda r: r["price"] == lowest})
        export_buttons(cdf, "competitor_prices")

        if mode.startswith("Auto"):
            # Simple feature-potential suggestion: match-but-not-undercut to protect margin.
            suggested = round(max(lowest - 1, your_price * 0.97), 2)
            st.markdown(glow_block(f"AED {suggested:,.2f}", "Suggested competitive price"),
                        unsafe_allow_html=True)

    # Price history chart.
    hist = db.get_price_history(item)
    if hist:
        st.markdown(section_label("📈 Price History"), unsafe_allow_html=True)
        hdf = pd.DataFrame(hist)
        fig = go.Figure()
        for source, grp in hdf.groupby("source"):
            fig.add_trace(go.Scatter(x=grp["captured_at"], y=grp["price"],
                                     mode="lines+markers", name=source))
        fig.update_layout(template="plotly_dark", height=320,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          margin=dict(l=10, r=10, t=10, b=10),
                          legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)


def render(nav=None) -> None:
    page_header("Pricing", "Calculate floors, recover buyboxes, track the market",
                icon="💰")
    t1, t2, t3 = st.tabs(["🧮 Calculator", "🏷️ Lost Buybox", "🛰️ Market Tracker"])
    with t1:
        _calculator()
    with t2:
        _lost_buybox()
    with t3:
        _market_tracker()
```

================================================================
FILE: modules/advertising.py
================================================================
```python
"""
modules/advertising.py
======================
📢 Advertising (Module 6).

  * Campaign overview (Ads API; mock): spend, ACoS, impressions, sales + KPIs.
  * Budget alarms: flashing banner + email/telegram when a campaign spends >20%
    over its daily average.
  * Prebuilt campaign generator: build a campaign from ad assets + trending
    keywords/products (api_client.create_campaign stub).
  * Ad Optimization: suggested bids per keyword/target and which ads to run.
"""

from __future__ import annotations
import pandas as pd
import streamlit as st

from core import db, notifier
from core.api_client import client
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, alert, badge

OVER = 1.20


def _overview(ads: pd.DataFrame) -> None:
    spend, sales = ads["spend_today"].sum(), ads["sales"].sum()
    acos = (spend / sales * 100) if sales else 0
    kpi_row([
        {"label": "Spend Today", "value": f"AED {spend:,.0f}", "accent": "blue"},
        {"label": "Ad Sales", "value": f"AED {sales:,.0f}", "accent": "emerald"},
        {"label": "Blended ACoS", "value": f"{acos:.1f}%",
         "accent": "amber" if acos > 20 else "emerald", "sub": "Target ≤ 20%"},
        {"label": "Impressions", "value": f"{ads['impressions'].sum()/1000:.1f}K",
         "accent": "violet"},
    ])


def _budget_alarm(ads: pd.DataFrame) -> None:
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    over = ads[ads["spend_today"] > ads["avg_daily"] * OVER]
    if over.empty:
        st.markdown(alert("All campaigns within budget guardrails.", kind="green", icon="✅"),
                    unsafe_allow_html=True)
        return
    names = ", ".join(over["campaign"].tolist())
    st.markdown(alert(f"BUDGET ALARM — {len(over)} campaign(s) >20% over daily avg: {names}",
                      kind="coral", icon="🚨", flash=True), unsafe_allow_html=True)
    c = st.columns([1, 1, 2])
    with c[0]:
        if st.button("➕ Add to Tasks", key="ad_task"):
            for _, r in over.iterrows():
                db.add_task(f"Cap budget: {r['campaign']}",
                            f"AED {r['spend_today']} vs AED {r['avg_daily']} avg.",
                            module="Advertising", priority="medium", related_id=r["campaign"])
            st.success("Tasks added.")
    with c[1]:
        if st.button("🔔 Notify", key="ad_notify"):
            res = notifier.notify_event("budget", "Ad budget alarm",
                                        f"Over budget: {names}")
            for ch, ok, msg in res:
                (st.success if ok else st.warning)(f"{ch}: {msg}")


def _table(ads: pd.DataFrame) -> None:
    st.markdown(section_label("📈 Campaigns"), unsafe_allow_html=True)
    disp = ads.copy()
    disp["over"] = disp.apply(lambda r: "Over" if r["spend_today"] > r["avg_daily"] * OVER else "OK", axis=1)
    styled_table(disp, highlight={
        "row-danger": lambda r: r["over"] == "Over",
        "row-warn": lambda r: r["acos"] > 25},
        badge_cols={"over": {"Over": ("⚠ Over", "coral"), "OK": ("✓ OK", "green")}})
    export_buttons(disp, "campaigns")


def _generator() -> None:
    st.markdown(section_label("🧱 Prebuilt Campaign Generator"), unsafe_allow_html=True)
    listings = client().get_my_listings()
    item = st.selectbox("Item to advertise", listings["title"].tolist(), key="gen_item")
    ctype = st.selectbox("Campaign type", ["Sponsored Products - Auto",
                                           "Sponsored Products - Exact", "Sponsored Brands"])
    budget = st.number_input("Daily budget (AED)", 10.0, value=150.0, step=10.0)

    row = listings[listings["title"] == item].iloc[0]
    targets = client().get_keyword_targets(item)
    st.caption("Suggested targets (trending keywords for this item):")
    styled_table(targets)

    if st.button("🚀 Build Campaign"):
        payload = {"name": f"{ctype.split(' - ')[0]} - {item}", "type": ctype,
                   "daily_budget": budget, "asin": row["asin"],
                   "keywords": targets["keyword"].tolist()}
        res = client().create_campaign(payload)
        db.add_task(f"Launch campaign: {payload['name']}",
                    f"Auto-built at AED {budget}/day with {len(payload['keywords'])} targets.",
                    module="Advertising", priority="medium")
        st.success(f"Campaign draft built ({res['status']}). Task added to launch it.")


def _optimization() -> None:
    st.markdown(section_label("🎯 Ad Optimization — bids & targets"), unsafe_allow_html=True)
    listings = client().get_my_listings()
    item = st.selectbox("Item", listings["title"].tolist(), key="opt_item")
    targets = client().get_keyword_targets(item)
    styled_table(targets, highlight={
        "row-good": lambda r: r["action"] == "Raise",
        "row-warn": lambda r: r["action"] == "Lower"},
        badge_cols={"action": {"Raise": ("↑ Raise", "green"), "Hold": ("→ Hold", "blue"),
                               "Lower": ("↓ Lower", "amber")}})
    export_buttons(targets, "ad_targets")
    st.caption("Recommendation: raise bids on low-ACoS targets, lower on high-ACoS, "
               "and shift budget to the best-performing keywords per item.")


def render(nav=None) -> None:
    page_header("Advertising", "Campaigns, budget alarms, generation & bid optimization",
                icon="📢")
    ads = client().get_campaigns()
    _overview(ads)
    _budget_alarm(ads)
    t1, t2, t3 = st.tabs(["📈 Campaigns", "🧱 Generate", "🎯 Optimize"])
    with t1:
        _table(ads)
    with t2:
        _generator()
    with t3:
        _optimization()
```

================================================================
FILE: modules/market_analysis.py
================================================================
```python
"""
modules/market_analysis.py
==========================
📊 Market Analysis (Module 7).

Compares your items vs the Amazon market, flags items that are trending AND
well-priced (→ suggest A+ content + ads), and recommends other levers per item
(e.g. "set a 10% coupon"). Findings feed into the central Tasks table.
"""

from __future__ import annotations
import streamlit as st

from core import db
from core.api_client import client
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge, alert


def _lever(row) -> str:
    """Recommend a growth lever per item from its signal + price gap."""
    if row["signal"] in ("Trending", "Hidden Gem") and row["your_price"] <= row["market_min"] * 1.05:
        return "Add A+ content + run ads"
    if row["your_price"] > row["market_min"] * 1.1:
        return "Set 10% coupon (price gap)"
    if row["signal"] == "Declining":
        return "Deal or clearance"
    return "Hold"


def render(nav=None) -> None:
    page_header("Market Analysis", "Where you stand vs the market — and what to do",
                icon="📊")
    df = client().get_market_comparison().copy()
    df["lever"] = df.apply(_lever, axis=1)
    df["price_gap"] = (df["your_price"] - df["market_min"]).round(0)

    trending = df[df["signal"].isin(["Trending", "Hidden Gem"])]
    kpi_row([
        {"label": "Items Analyzed", "value": str(len(df)), "accent": "blue"},
        {"label": "Trending", "value": str(len(trending)), "accent": "emerald",
         "sub": "Promote these"},
        {"label": "Overpriced vs Market",
         "value": str(int((df["your_price"] > df["market_min"] * 1.1).sum())),
         "accent": "amber", "sub": "Coupon candidates"},
    ])
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    if not trending.empty:
        st.markdown(alert(f"{len(trending)} trending + well-priced items — prime for A+ "
                          f"content and ads.", kind="green", icon="🚀"), unsafe_allow_html=True)

    st.markdown(section_label("Your Items vs Market"), unsafe_allow_html=True)
    styled_table(df, highlight={
        "row-good": lambda r: r["signal"] in ("Trending", "Hidden Gem"),
        "row-warn": lambda r: r["signal"] == "Declining"},
        badge_cols={"lever": {
            "Add A+ content + run ads": ("🚀 A+ & Ads", "green"),
            "Set 10% coupon (price gap)": ("🎟️ 10% Coupon", "blue"),
            "Deal or clearance": ("🔥 Deal", "amber"),
            "Hold": ("→ Hold", "violet")},
            "signal": {"Trending": ("Trending", "green"), "Hidden Gem": ("Hidden Gem", "green"),
                       "Stable": ("Stable", "blue"), "Declining": ("Declining", "amber")}})
    export_buttons(df, "market_analysis")

    if st.button("➕ Turn recommendations into Tasks"):
        for _, r in df[df["lever"] != "Hold"].iterrows():
            db.add_task(f"{r['lever']}: {r['item']}",
                        f"Signal {r['signal']}, you AED {r['your_price']} vs market AED {r['market_min']}.",
                        module="Market Analysis", priority="medium", related_id=r["item"])
        st.success("Recommendations added to Tasks.")
```

================================================================
FILE: modules/deals.py
================================================================
```python
"""
modules/deals.py
================
🔥 Deals (Module 8).

Pulls Amazon's suggested-for-deals items (api_client; mock) and recommends the
best deal price per item, showing the resulting margin. Export + push to Tasks.
"""

from __future__ import annotations
import streamlit as st

from core import db
from core.api_client import client
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge


def render(nav=None) -> None:
    page_header("Deals", "Amazon deal candidates and the best price to offer", icon="🔥")
    df = client().get_deal_suggestions().copy()
    df["discount_%"] = ((1 - df["suggested_deal_price"] / df["current_price"]) * 100).round(0)

    kpi_row([
        {"label": "Deal Candidates", "value": str(len(df)), "accent": "blue"},
        {"label": "Avg Discount", "value": f"{df['discount_%'].mean():.0f}%", "accent": "amber"},
        {"label": "Min Margin Kept", "value": f"{df['margin_pct'].min():.0f}%", "accent": "emerald"},
    ])
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown(section_label("Suggested Deals"), unsafe_allow_html=True)
    styled_table(df, highlight={"row-good": lambda r: r["margin_pct"] >= 30},
                 badge_cols={"deal_type": {
                     "Lightning Deal": ("⚡ Lightning", "violet"),
                     "7-Day Deal": ("📅 7-Day", "blue"),
                     "Best Deal": ("🏆 Best Deal", "green")}})
    export_buttons(df, "deal_suggestions")

    if st.button("➕ Add deals to Tasks"):
        for _, r in df.iterrows():
            db.add_task(f"Submit {r['deal_type']}: {r['item']}",
                        f"Deal price AED {r['suggested_deal_price']} "
                        f"(−{r['discount_%']:.0f}%), keeps {r['margin_pct']}% margin.",
                        module="Deals", priority="medium", related_id=r["item"])
        st.success("Deals added to Tasks.")
```

================================================================
FILE: modules/assets.py
================================================================
```python
"""
modules/assets.py
=================
🎨 Asset Management (Module 9).

  * Suggests A+ content per item and shows ready A+ content synced from a sheet
    (mock via api/inventory source).
  * Pulls published video links (from inventory website / sheet) and shows
    per-item status: Uploaded (green) / Not Uploaded (amber).
"""

from __future__ import annotations
import streamlit as st

from core import db, inventory_source, mock_data
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge


def render(nav=None) -> None:
    page_header("Asset Management", "A+ content suggestions and video upload status",
                icon="🎨")

    df = mock_data.asset_status().copy()
    videos = inventory_source.fetch_video_links()  # mock pulls from same source

    uploaded = int((df["video_status"] == "Uploaded").sum())
    aplus_ready = int((df["aplus_status"] == "Ready").sum())
    kpi_row([
        {"label": "Items", "value": str(len(df)), "accent": "blue"},
        {"label": "A+ Ready", "value": str(aplus_ready), "accent": "emerald"},
        {"label": "Videos Uploaded", "value": f"{uploaded}/{len(df)}", "accent": "violet"},
        {"label": "Videos Pending", "value": str(len(df) - uploaded), "accent": "amber"},
    ])
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown(section_label("A+ Content & Video Status"), unsafe_allow_html=True)
    styled_table(df, highlight={
        "row-good": lambda r: r["video_status"] == "Uploaded",
        "row-warn": lambda r: r["video_status"] == "Not Uploaded"},
        badge_cols={
            "aplus_status": {"Ready": ("✓ Ready", "green"), "Draft": ("Draft", "amber"),
                             "Suggested": ("Suggested", "violet")},
            "video_status": {"Uploaded": ("✓ Uploaded", "green"),
                             "Not Uploaded": ("⏳ Not Uploaded", "amber")}})
    export_buttons(df, "asset_status")

    st.markdown(section_label("Suggested A+ Modules"), unsafe_allow_html=True)
    for _, r in df[df["aplus_status"] != "Ready"].iterrows():
        st.markdown(
            f"<div class='glass-card' style='margin-bottom:8px; padding:13px 16px'>"
            f"<b>{r['item']}</b> — suggest: comparison chart, lifestyle banner, "
            f"feature callouts, brand story. {badge('Create A+', 'blue')}</div>",
            unsafe_allow_html=True)

    if st.button("➕ Add asset tasks"):
        for _, r in df[(df["aplus_status"] != "Ready") | (df["video_status"] == "Not Uploaded")].iterrows():
            db.add_task(f"Produce assets: {r['item']}",
                        f"A+ {r['aplus_status']}, video {r['video_status']}.",
                        module="Asset Management", priority="low", related_id=r["item"])
        st.success("Asset tasks added.")
```

================================================================
FILE: modules/aplus_studio.py
================================================================
```python
"""
modules/aplus_studio.py
=======================
✨ A+ Content Studio (new module).

Turns any product brief / spec sheet / brochure into a complete, production-ready
Amazon Premium A+ Content package following a strict A+ Content Architect system
prompt. Extended for Amazon.ae: every copy field and every in-image text overlay
is produced BILINGUALLY in English + Arabic.

Inputs:
  * a typed product brief, and/or
  * an uploaded spec file (PDF / TXT / CSV / XLSX) whose text is extracted,
  * an optional product reference image (shown for the operator).

Generation is routed through assistant.complete() → Anthropic (model in
assistant.MODEL). Without an API key it shows a clear setup message (this module
needs the model — it can't be faked with rules). Output is shown rendered + as
raw copyable text, and is downloadable as a .md file.
"""

from __future__ import annotations
import io
import re
import zipfile
import streamlit as st

from core import db, assistant, imagegen
from core.components import page_header
from core.styles import section_label, badge, alert


# ---------------------------------------------------------------------------
# SYSTEM PROMPT (the A+ Content Architect spec) + bilingual Arabic addendum
# ---------------------------------------------------------------------------
APLUS_SYSTEM_PROMPT = r"""You are a senior Amazon A+ Content Architect and Creative Director. You work as the strategic brain of a lean AI content team. Your role is to analyze any product file, brochure, spec sheet, or brief that I upload or describe, and produce a complete, production-ready Amazon Premium A+ Content Package — with zero hardcoding, fully adapted to whatever product I give you.

Your output must be so thorough and precise that:
- The human designer only assembles — they never have to think, decide, or write anything
- The operator can paste each image prompt directly into ChatGPT gpt-image-2 without editing
- The entire content set — images generated, designed, and uploaded — is completed within 1 hour

YOUR TEAM ROLES:
You = Product analysis, content strategy, module selection, copywriting, image direction, gpt-image-2 prompts
ChatGPT gpt-image-2 = Image generation from your prompts
Human Designer = Cropping, resizing, text overlays, final QC, Amazon upload

STEP 1 — PRODUCT ANALYSIS (do this silently before writing anything)
Extract and understand: product name and full model name; product category and type; core unique selling points; key features (list every feature mentioned); technical specifications (dimensions, power, capacity, materials, etc.); included accessories / package contents; target customer (who is this for, what problem does it solve); brand tone (premium, budget, tech, lifestyle, family, professional, etc.); any taglines, marketing language, or emotional hooks already present.
From this analysis decide independently: how many modules the A+ page needs (minimum 4, maximum 7 for Premium A+); which module type is best for each section following the strict priority rules in Step 2; the narrative flow (hook -> key feature -> supporting features -> specs/value -> emotional close); the copy for every field; the scene for every image.

STEP 2 — MODULE SELECTION RULES AND PRIORITY
TIME IS CRITICAL. Default to single-image modules; only use multi-image modules when there is no better option.
SIMPLE BANNER — use freely, no limit. Opening hero, emotional close, full-width visual moments. Always 1 image.
PREMIUM SINGLE IMAGE WITH TEXT — your default workhorse module, use as much as possible. Any single feature/benefit/spec/accessory/use case/emotional story. Always 1 image. When in doubt, use this.
PREMIUM DUAL IMAGES WITH TEXT — maximum ONCE per page, only when two features are so closely related that splitting them weakens the story (two modes side by side, before/after). Requires 2 images.
PREMIUM FOUR IMAGES WITH TEXT — maximum ONCE per page, last resort, only for exactly 4 equal sub-features/steps. Each image is tiny (220x220px min); detail is lost; costs 4 generations. Avoid unless no alternative.
COMPARISON CHART — maximum ONCE per page, no images. Text-only table for clear competitive advantages; a good filler that costs zero image time.
MODULE COUNT BUDGET: total 4–7 modules; aim for 4–5 total images; never exceed 6 total images. If approaching 6, replace the next multi-image module with a Single Image module or a Comparison Chart. Count total images before finalizing; if over 6, revise.

STEP 3 — DIMENSION RULES (apply exactly)
SIMPLE BANNER: desktop 1464x600px min; mobile 600x450px min; AI generation 2000x2000px square (designer crops after).
PREMIUM SINGLE IMAGE WITH TEXT: upload 800x600px min; AI generation 2000x2000px square.
PREMIUM DUAL IMAGES WITH TEXT: each image 650x350px min; AI generation 2000x2000px square per image.
PREMIUM FOUR IMAGES WITH TEXT: each image 220x220px min; AI generation 2000x2000px square per image.
COMPARISON CHART: no image — text and table only.

STEP 4 — COPY RULES (apply exactly)
Write all copy yourself. Never leave a field blank, never use placeholder text, never write "TBD".
Character limits by field (always label each field with its limit): Simple Banner title max 300; Single Image Headline 1 max 40; Single Image Headline 2 max 80; Single Image Body max 500; Dual Image Headline per block max 50; Dual Image Body per block max 300; Four Image Headline per block max 50; Four Image Body per block max 150.
Tone: match the brand tone; lead with the customer benefit not the feature; active voice; avoid jargon unless the customer is technical; every body text answers what is it, why it matters, who it is for.

STEP 5 — IMAGE PROMPT RULES (apply exactly)
Prompts must be detailed, cinematic, feature-specific, correct on first attempt. Write as flowing paragraphs (not bullets), minimum 180 words each, containing all 7 elements in this exact order:
ELEMENT 1 — CAMERA ANGLE AND PERSPECTIVE: state the exact angle at the very start. Choose from: straight-on front view, 3/4 front-left, 3/4 front-right, side profile, rear 3/4, top-down overhead flat-lay, extreme close-up macro, low angle looking upward, eye-level lifestyle, interior open-view, or over-the-shoulder human interaction. Angle must match the feature. Every module uses a DIFFERENT angle — never repeat.
ELEMENT 2 — FULL SCENE AND ENVIRONMENT: room/outdoor environment, exact surface, background elements and distances, lifestyle props, time of day / light feel, dominant color palette, emotional atmosphere. Be highly specific.
ELEMENT 3 — LIGHTING DIRECTION AND QUALITY: primary light source type, direction, hard vs soft shadows, color temperature in Kelvin, secondary/fill details.
ELEMENT 4 — PRODUCT IDENTITY AND ANGLE FREEDOM: include this exact paragraph verbatim in every prompt: "Use the uploaded product reference image as the sole identity source. Faithfully reproduce the product's overall silhouette, color scheme, surface finish, material texture, branding marks, labels, logos, and all distinguishing design details. You are not cloning the reference photograph — you are placing the same product into the new scene and camera angle described above. You have full freedom to rotate, reposition, and reframe the product to match the specified angle. All text, logos, and labels that are naturally visible from this new angle must be rendered sharp, accurate, and fully legible."
ELEMENT 5 — FEATURE STORYTELLING AND VISUAL FOCUS: name the exact feature; describe how it is demonstrated; if a person is in frame specify hand/gesture/part/expression; if pure product, how composition and light direct the eye.
ELEMENT 6 — TEXT OVERLAY IN THE IMAGE: one short graphic phrase naming the feature; exact phrase, precise position, visual treatment. Text never overlaps the product and is instantly readable.
ELEMENT 7 — FINAL QUALITY AND FORMAT INSTRUCTION: end every prompt with this exact sentence: "Photorealistic commercial product photography quality, ultra-sharp focus on the product, no illustration style, no graphic design style, no cartoon rendering. Square format, 2000x2000 pixels, 1:1 ratio."

STEP 6 — OUTPUT FORMAT (use this exact structure every time)
=== PRODUCT ANALYSIS SUMMARY ===
Product name / Category / Key USPs (bullets) / Key features (bullets) / Specs (bullets) / Accessories-contents (bullets) / Target customer / Brand tone / Total images planned (6 or fewer) / Narrative strategy (2-3 sentences).
=== A+ CONTENT PACKAGE ===
Total modules / Total images to generate / Estimated design time (minutes).
--- MODULE (n) — (TYPE NAME) ---
Purpose (1 sentence). DIMENSIONS (upload size / mobile if applicable / AI generation 2000x2000px 1:1). DESIGN INSTRUCTION FOR DESIGNER. COPY (every field with label + char limit + full copy). GPT-IMAGE-2 PROMPT (full, min 180 words, all 7 elements in order). Repeat per module.
=== IMAGE GENERATION QUEUE === operator instructions + per-image lines: Image (n): (filename.jpg) — Module (n) — (angle + scene summary), then the full prompt repeated for direct copy-paste.
=== DESIGNER ASSEMBLY CHECKLIST === Phase 1 receive filenames; Phase 2 crop/resize each to exact pixels with crop focus; Phase 3 text overlays (module, exact text, font suggestion, placement); Phase 4 Amazon Seller Central upload steps per module.
=== QUICK REFERENCE TABLE === Module | Type | Amazon Upload Size | AI Generate Size | Filename (one row per module).

IMPORTANT BEHAVIORS (override everything on conflict):
Never output a hardcoded example — analyze the given product and build fresh. Never ask the user to fill copy or decide — you decide and write everything. Never include placeholder text. Each image prompt is minimum 180 words — count before finalizing. Every module uses a different camera angle — audit before finalizing. Total images never exceed 6 — count before finalizing. Dual-image module max once; four-image module max once. Default module is Single Image with Text. Maintain narrative flow Hook -> Core Value -> Features -> Proof/Specs -> Emotional Close. The last module is always an emotional lifestyle banner, never a spec/feature module. The hero banner (Module 1) always uses a wide 3/4 lifestyle angle with the full product in its environment. Macro/close-up angles are reserved for controls/texture/detail/interface modules. Overhead flat-lay is reserved for accessories/package contents/unboxing. Lifestyle angles with people are reserved for use-case and emotional modules.

=== ADDITIONAL REQUIREMENT — BILINGUAL ENGLISH + ARABIC (Amazon.ae) ===
This store sells on Amazon.ae, so every deliverable is bilingual English + Arabic.
COPY: For every copy field, output the English text (with its character-limit label) AND directly beneath it an Arabic translation labelled "Arabic (العربية):". The Arabic must be natural, professional Modern Standard Arabic suited to the brand tone (unless the brief specifies Gulf/Khaleeji dialect or "English only"), written right-to-left, benefit-led, never a literal machine translation, and should respect the same character-limit spirit as the English.
IMAGE TEXT OVERLAY (Element 6): every image's embedded text phrase must be given in BOTH English and Arabic. In the gpt-image-2 prompt, state the exact English phrase AND the exact Arabic phrase (give the literal Arabic string to render), specify that the Arabic appears directly beneath the English (or beside it), and instruct the model to render the Arabic in correct right-to-left order with properly connected Arabic letterforms, fully legible, in a clean modern Arabic sans-serif. The bilingual overlay must never overlap the product and stays instantly readable. This is part of Element 6 and does not reduce the other elements or the 180-word minimum.
DESIGNER ASSEMBLY CHECKLIST + QUICK REFERENCE: wherever text overlays are listed, list BOTH the English and the exact Arabic string per module so the designer can place both.
If the brief explicitly requests a specific Arabic dialect or "English only", follow that instruction over this bilingual default.

Analyze the product brief that follows and produce the complete package immediately."""


# ---------------------------------------------------------------------------
# File text extraction (PDF / TXT / CSV / XLSX)
# ---------------------------------------------------------------------------
def _extract_text(upload) -> str:
    """Best-effort text extraction from an uploaded spec file."""
    name = upload.name.lower()
    try:
        if name.endswith(".txt"):
            return upload.getvalue().decode("utf-8", errors="ignore")
        if name.endswith(".csv"):
            import pandas as pd
            return pd.read_csv(upload).to_csv(index=False)
        if name.endswith(".xlsx"):
            import pandas as pd
            sheets = pd.read_excel(upload, sheet_name=None)
            return "\n\n".join(f"# Sheet: {s}\n{df.to_csv(index=False)}"
                               for s, df in sheets.items())
        if name.endswith(".pdf"):
            try:
                from pypdf import PdfReader
            except Exception:
                return "[PDF uploaded but 'pypdf' is not installed — run: pip install pypdf]"
            reader = PdfReader(io.BytesIO(upload.getvalue()))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as e:
        return f"[Could not read {upload.name}: {e}]"
    return ""


# ---------------------------------------------------------------------------
# Pull the gpt-image prompts out of the generated package so we can render them
# ---------------------------------------------------------------------------
def _extract_image_prompts(package: str) -> list[dict]:
    """Return [{'label','prompt'}] parsed from the package text.

    Primary source: each module's 'GPT-IMAGE-2 PROMPT:' block. Falls back to the
    'Prompt:' lines in the IMAGE GENERATION QUEUE if needed.
    """
    out = []
    # Module prompt blocks: capture text up to the next '--- MODULE', '===', or EOF.
    for m in re.finditer(r"GPT-IMAGE-2 PROMPT:\s*(.+?)(?=\n\s*---|\n\s*===|\Z)",
                         package, re.DOTALL | re.IGNORECASE):
        text = m.group(1).strip()
        if len(text) > 40:
            out.append(text)
    if not out:  # fallback to the queue's Prompt: lines
        for m in re.finditer(r"Prompt:\s*(.+?)(?=\n\s*Image \d|\n\s*===|\Z)",
                             package, re.DOTALL | re.IGNORECASE):
            text = m.group(1).strip()
            if len(text) > 40:
                out.append(text)
    # de-dupe while keeping order
    seen, uniq = set(), []
    for t in out:
        k = t[:120]
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return [{"label": f"Image {i+1}", "prompt": t} for i, t in enumerate(uniq)]


def _queue_filenames(package: str) -> list[str]:
    """Pull the filenames the model assigned in the IMAGE GENERATION QUEUE, in
    order (e.g. 'module2_hero.jpg'), so downloads can be named meaningfully."""
    names = []
    for m in re.finditer(r"Image\s*\d+\s*:\s*\(?([^\s()]+\.(?:jpg|jpeg|png|webp))\)?",
                         package, re.IGNORECASE):
        names.append(m.group(1))
    return names


def _build_images_zip(generated: dict, package: str) -> bytes:
    """Zip all generated images (PNG bytes), named from the queue when available."""
    qnames = _queue_filenames(package)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i in sorted(generated):
            stem = (qnames[i].rsplit(".", 1)[0] if i < len(qnames) else f"aplus_image_{i+1}")
            z.writestr(f"{stem}.png", generated[i])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def render(nav=None) -> None:
    page_header("A+ Content Studio",
                "Any product brief → a full, bilingual (EN/AR) Premium A+ Content package",
                icon="✨")

    has_key = bool(db.get_setting("anthropic_api_key", ""))
    st.markdown(
        badge(f"Live Claude ({assistant.MODEL})" if has_key
              else "Add an Anthropic API key in Settings to enable generation",
              "green" if has_key else "amber"),
        unsafe_allow_html=True)

    st.markdown(section_label("1 · Product input"), unsafe_allow_html=True)
    brief = st.text_area(
        "Product brief / description",
        height=200,
        placeholder="Paste the product brief, spec sheet text, or a description here.\n"
                    "Example: 'Powerology 30000mAh Power Bank, 65W USB-C PD, digital "
                    "display, charges laptop + phone, aluminium body, includes USB-C cable…'")

    files = st.file_uploader(
        "Optional: upload spec sheet / brochure (PDF, TXT, CSV, XLSX) — text is extracted",
        type=["pdf", "txt", "csv", "xlsx"], accept_multiple_files=True)

    col = st.columns([2, 1])
    with col[0]:
        ref_imgs = st.file_uploader(
            "Optional: product reference image(s) — select several at once, or add "
            "them one by one (they accumulate)",
            type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
            key="aplus_ref_uploader")
    with col[1]:
        dialect = st.selectbox("Arabic style",
                               ["Modern Standard Arabic (default)",
                                "Gulf / Khaleeji dialect", "English only"])

    # Accumulate reference images across uploads (so adding them one at a time also
    # works, not only multi-select in the OS dialog). Keyed by name+size.
    store = st.session_state.setdefault("aplus_ref_store", {})
    for f in (ref_imgs or []):
        store[f"{f.name}:{f.size}"] = {"name": f.name, "bytes": f.getvalue()}

    if store:
        cc = st.columns([1, 1, 2])
        cc[0].markdown(badge(f"{len(store)} reference image(s)", "green"),
                       unsafe_allow_html=True)
        if cc[1].button("🗑 Clear images"):
            store.clear()
            st.rerun()
        thumbs = st.columns(min(max(len(store), 1), 5))
        for i, item in enumerate(store.values()):
            with thumbs[i % len(thumbs)]:
                st.image(item["bytes"], caption=item["name"], width=120)

    # Expose for the package prompt + the image generator.
    st.session_state["aplus_ref_images"] = [v["bytes"] for v in store.values()]
    st.session_state["aplus_ref_names"] = [v["name"] for v in store.values()]

    st.markdown(section_label("2 · Generate"), unsafe_allow_html=True)
    go = st.button("✨ Generate A+ Content Package", use_container_width=True, type="primary")

    if go:
        # Assemble the product context.
        parts = []
        if brief.strip():
            parts.append("PRODUCT BRIEF (typed):\n" + brief.strip())
        for f in files or []:
            text = _extract_text(f)
            if text.strip():
                parts.append(f"FILE: {f.name}\n{text.strip()}")
        combined = "\n\n".join(parts)[:24000]  # cap to control token use

        if not combined.strip():
            st.markdown(alert("Add a product brief or upload a spec file first.",
                              kind="amber", icon="⚠️"), unsafe_allow_html=True)
            return
        if not has_key:
            st.markdown(alert("This studio needs the Anthropic model to write the package. "
                              "Open Settings → AI & Amazon → paste your Anthropic API key, "
                              "then come back.", kind="amber", icon="🔑"),
                        unsafe_allow_html=True)
            return

        # Dialect instruction appended to the user message.
        dialect_note = {
            "Modern Standard Arabic (default)": "Use professional Modern Standard Arabic for all Arabic text.",
            "Gulf / Khaleeji dialect": "Use natural Gulf/Khaleeji Arabic for all Arabic text.",
            "English only": "Produce ENGLISH ONLY — skip the Arabic translations and Arabic overlays.",
        }[dialect]
        ref_names = st.session_state.get("aplus_ref_names", [])
        ref_note = (f"yes — {', '.join(ref_names)}" if ref_names else "not attached here")
        user_prompt = (f"{dialect_note}\n\nProduct reference image(s) provided to the operator: "
                       f"{ref_note}.\n\n{combined}")

        with st.spinner("Architecting your A+ package (analysis → modules → copy → image prompts)…"):
            result, status = assistant.complete(APLUS_SYSTEM_PROMPT, user_prompt, max_tokens=14000)

        if status != "ok":
            msg = ("No Anthropic API key set in Settings." if status == "no_key"
                   else f"Generation failed — {status}")
            st.markdown(alert(msg, kind="coral", icon="⛔"), unsafe_allow_html=True)
            return

        st.session_state["aplus_result"] = result
        # Log a task so it shows up in the central feed.
        first_line = brief.strip().splitlines()[0] if brief.strip() else (files[0].name if files else "product")
        db.add_task(f"Produce A+ content: {first_line[:50]}",
                    "Package generated in A+ Content Studio — assign to designer.",
                    module="A+ Content Studio", priority="medium")

    # Display last result.
    result = st.session_state.get("aplus_result")
    if not result:
        return

    st.markdown("---")
    st.markdown(section_label("3 · Your A+ Content Package"), unsafe_allow_html=True)
    st.download_button("⬇ Download package (.md)", result.encode("utf-8"),
                       file_name="aplus_content_package.md", mime="text/markdown",
                       use_container_width=True)
    tab_view, tab_copy = st.tabs(["📖 Rendered", "📋 Raw (copy)"])
    with tab_view:
        st.markdown(result)
    with tab_copy:
        st.code(result, language="markdown")

    _image_generation_section(result)


# ---------------------------------------------------------------------------
# Image generation (turns the prompts into actual pictures via OpenAI)
# ---------------------------------------------------------------------------
def _image_generation_section(package: str) -> None:
    st.markdown("---")
    st.markdown(section_label("4 · Generate the images"), unsafe_allow_html=True)

    has_img_key = imagegen.has_image_key()
    st.markdown(
        badge(f"Image model: {imagegen.image_model()}" if has_img_key
              else "Add an OpenAI API key in Settings → AI & Amazon to generate images",
              "green" if has_img_key else "amber"),
        unsafe_allow_html=True)

    ref_images = st.session_state.get("aplus_ref_images", [])
    if ref_images:
        st.caption(f"Using {len(ref_images)} reference image(s) to keep the product identity "
                   f"consistent across all generated scenes.")
    else:
        st.caption("Tip: upload product reference image(s) above so the generated images "
                   "match your real product. Without them, images are generated from the prompt only.")

    prompts = _extract_image_prompts(package)
    if not prompts:
        st.info("No gpt-image prompts were detected in the package text.")
        return

    size = st.selectbox("Output size", imagegen.SUPPORTED_SIZES, index=0,
                        help="API renders up to 1536px; the designer upscales to 2000px for Amazon.")

    if "aplus_images" not in st.session_state:
        st.session_state["aplus_images"] = {}

    cgen = st.columns([1, 3])
    with cgen[0]:
        gen_all = st.button("🎨 Generate ALL", use_container_width=True, disabled=not has_img_key)
    with cgen[1]:
        st.caption(f"{len(prompts)} image prompt(s) detected. Generating all calls the image "
                   f"API once per prompt (this costs money on your OpenAI account).")

    if gen_all and has_img_key:
        prog = st.progress(0.0)
        for i, p in enumerate(prompts):
            data, status = imagegen.generate_image(p["prompt"], ref_images, size=size)
            if status == "ok":
                st.session_state["aplus_images"][i] = data
            else:
                st.warning(f"{p['label']}: {status}")
            prog.progress((i + 1) / len(prompts))
        st.success("Done generating.")

    # Download-all-as-ZIP (named from the package's Image Generation Queue).
    generated = {i: b for i, b in st.session_state["aplus_images"].items() if b}
    if generated:
        st.download_button(
            f"⬇ Download ALL {len(generated)} image(s) as ZIP",
            _build_images_zip(generated, package),
            file_name="aplus_images.zip", mime="application/zip",
            use_container_width=True, key="aplus_zip_all")

    # Per-image cards.
    for i, p in enumerate(prompts):
        st.markdown(f"**🖼️ {p['label']}**")
        c1, c2 = st.columns([2, 1])
        with c1:
            with st.expander("View the prompt", expanded=False):
                st.code(p["prompt"], language="text")
        with c2:
            if st.button(f"Generate {p['label']}", key=f"genimg_{i}",
                         use_container_width=True, disabled=not has_img_key):
                with st.spinner(f"Generating {p['label']}…"):
                    data, status = imagegen.generate_image(p["prompt"], ref_images, size=size)
                if status == "ok":
                    st.session_state["aplus_images"][i] = data
                else:
                    st.warning(status if status != "no_key"
                               else "Add your OpenAI API key in Settings.")
        img = st.session_state["aplus_images"].get(i)
        if img:
            st.image(img, width=360)
            st.download_button("⬇ Download", img, file_name=f"aplus_image_{i+1}.png",
                               mime="image/png", key=f"dl_img_{i}")
        st.divider()
```

================================================================
FILE: modules/fba.py
================================================================
```python
"""
modules/fba.py
==============
🚚 FBA / Amazon Warehouse Optimization (Module 10).

Upload (or use mock) the items currently in Amazon's warehouse, then analyze:
  * RESEND — good sellers running low → units to resend (velocity × cover − on hand).
  * STUCK  — aged inventory with low velocity → recommend more ads or price cut.
"""

from __future__ import annotations
import math
import pandas as pd
import streamlit as st

from core import db
from core.api_client import client
from core.util import get_field
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge


def _analyze(df: pd.DataFrame, cover_days: int) -> pd.DataFrame:
    overrides = db.get_channel_overrides()  # FBA/FBM decisions from Hazmat
    rows = []
    for _, r in df.iterrows():
        vel = float(r["daily_velocity"])
        units = int(r["fba_units"])
        days_left = round(units / vel, 1) if vel else 999
        channel = overrides.get(r["sku"], "FBA")

        if channel == "FBM":
            # Merchant-fulfilled — never recommend an FBA resend for these.
            verdict, resend, action = "FBM", 0, "Merchant-fulfilled — exclude from FBA resend"
        else:
            stuck = vel < 0.4 and int(r["days_in_fba"]) > 60
            resend = max(math.ceil(vel * cover_days) - units, 0) if not stuck else 0
            verdict = "STUCK" if stuck else ("RESEND" if resend > 0 else "OK")
            action = ("More ads / price cut" if stuck else
                      ("Resend to FBA" if resend > 0 else "Hold"))

        rows.append({
            "sku": r["sku"], "title": r["title"], "channel": channel,
            "fba_units": units, "velocity/day": vel,
            "days_in_fba": int(r["days_in_fba"]), "days_left": days_left,
            "resend_units": resend, "verdict": verdict, "action": action,
        })
    return pd.DataFrame(rows)


def render(nav=None) -> None:
    page_header("FBA / Warehouse Optimization",
                "What to resend, and what's stuck and needs a push", icon="🚚")

    up = st.file_uploader("Amazon warehouse (FBA) inventory file (CSV/Excel)",
                          type=["csv", "xlsx"], key="fba_up")
    if up:
        raw = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
        df = pd.DataFrame({
            "sku": get_field(raw, "sku", ""), "title": get_field(raw, "title", ""),
            "fba_units": get_field(raw, "qty", 0),
            "daily_velocity": get_field(raw, "velocity", 0).fillna(0)
                if "velocity" in [c.lower() for c in raw.columns] else 0.5,
            "days_in_fba": 30})
        src = f"uploaded ({up.name})"
    else:
        df = client().get_fba_inventory()
        src = "mock FBA inventory (upload to override)"
    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)

    cover = st.slider("Target FBA cover (days)", 14, 90, 30)
    res = _analyze(df, cover)

    resend_n = int((res["verdict"] == "RESEND").sum())
    stuck_n = int((res["verdict"] == "STUCK").sum())
    fbm_n = int((res["verdict"] == "FBM").sum())
    kpi_row([
        {"label": "SKUs in FBA", "value": str(len(res)), "accent": "blue"},
        {"label": "To Resend", "value": str(resend_n), "accent": "emerald",
         "sub": f"{int(res['resend_units'].sum())} units total"},
        {"label": "Stuck", "value": str(stuck_n), "accent": "coral",
         "sub": "Aged + slow"},
        {"label": "FBM (excluded)", "value": str(fbm_n), "accent": "violet",
         "sub": "Merchant-fulfilled"},
    ])
    if fbm_n:
        st.caption(f"{fbm_n} item(s) marked FBM in Hazmat are excluded from FBA resend.")
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown(section_label("FBA Analysis"), unsafe_allow_html=True)
    styled_table(res, highlight={
        "row-danger": lambda r: r["verdict"] == "STUCK",
        "row-good": lambda r: r["verdict"] == "RESEND",
        "row-warn": lambda r: r["verdict"] == "FBM"},
        badge_cols={"verdict": {"STUCK": ("STUCK", "coral"), "RESEND": ("RESEND", "green"),
                                "OK": ("OK", "blue"), "FBM": ("FBM (skip)", "violet")},
                    "channel": {"FBA": ("FBA", "blue"), "FBM": ("FBM", "violet")}})
    export_buttons(res, "fba_optimization")

    if st.button("➕ Add FBA actions to Tasks"):
        for _, r in res[res["verdict"].isin(["RESEND", "STUCK"])].iterrows():
            db.add_task(f"{r['verdict']}: {r['title']}",
                        (f"Resend {r['resend_units']} units." if r["verdict"] == "RESEND"
                         else f"Stuck {r['days_in_fba']}d — {r['action']}."),
                        module="FBA / Warehouse Optimization",
                        priority="high" if r["verdict"] == "STUCK" else "medium",
                        related_id=r["sku"])
        st.success("FBA tasks added.")
```

================================================================
FILE: modules/hazmat_inactive.py
================================================================
```python
"""
modules/hazmat_inactive.py
==========================
☣️ Hazmat & Inactive (new module). Two parts:

PART 1 — HAZMAT (FBA Dangerous Goods compliance)
  Monitors the FBA Compliance Dashboard (via api_client; mock now, real API later
  — sellercentral.amazon.ae/fba/compliance-dashboard). Maps each item's status:
    * "Unable to classify"            -> generate a Battery Exemption sheet and
                                         upload it (button generates an upload-ready
                                         .xlsx using Amazon's exact template).
    * "Dangerous Good FBA Fulfillable"-> APPROVED -> set fulfilment channel to FBA.
    * "Dangerous Good Unfulfillable"  -> NOT approved -> set fulfilment channel FBM.
  Actions call api_client stubs and log tasks.

PART 2 — INACTIVE
  Lists inactive listings with the reason, Export, and one-click tasks to fix.

You can also upload the dashboard's own export (CSV/Excel) instead of mock data.
"""

from __future__ import annotations
import io
import pandas as pd
import streamlit as st

from core import db, mock_data
from core.api_client import client
from core.util import get_field
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, badge, alert


# ---------------------------------------------------------------------------
# Status classification
# ---------------------------------------------------------------------------
def _hazmat_bucket(status: str) -> str:
    s = str(status).strip().lower()
    if "unable" in s:
        return "unable"
    if "unfulfil" in s:          # unfulfillable (check before fulfillable!)
        return "unfulfillable"
    if "fulfil" in s:
        return "fulfillable"
    return "other"


_ACTION = {
    "unable":        "Generate & upload hazmat exemption sheet",
    "fulfillable":   "Approved → set fulfilment channel to FBA",
    "unfulfillable": "Not approved → set fulfilment channel to FBM",
    "other":         "Review manually",
}
_BADGE = {
    "unable": ("⚠ Unable to classify", "amber"),
    "fulfillable": ("✓ FBA Fulfillable (approved)", "green"),
    "unfulfillable": ("✗ Unfulfillable", "coral"),
    "other": ("Review", "violet"),
}


# ---------------------------------------------------------------------------
# Battery exemption sheet generator (Amazon's exact template + dropdowns)
# ---------------------------------------------------------------------------
def build_battery_exemption_xlsx(items: pd.DataFrame) -> bytes:
    """Return an upload-ready .xlsx pre-filled with ASIN + title for the given
    items, with Amazon's exact headers and data-validation dropdowns on the
    battery columns. The remaining cells are left for the user/operator to fill.
    """
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Battery exemption sheet"
    ws.append(mock_data.HAZMAT_TEMPLATE_HEADERS)
    for _, r in items.iterrows():
        ws.append([r.get("asin", ""), r.get("title", ""), "", "", "", "", "", "", "", ""])

    # Hidden sheet holding the allowed dropdown values.
    lists = wb.create_sheet("Lists")
    a = mock_data.HAZMAT_ALLOWED
    columns = {"A": a["sold"], "B": a["chemical"], "C": a["packaging"],
               "D": a["cells"], "E": a["watt_hours"], "F": a["spillability"]}
    for col, vals in columns.items():
        for i, v in enumerate(vals, start=1):
            lists[f"{col}{i}"] = v
    lists.sheet_state = "hidden"

    last_row = ws.max_row + 100  # allow extra manual rows
    # (sheet column letter, lists column, value count)
    dv_map = [("D", "A", len(a["sold"])), ("E", "B", len(a["chemical"])),
              ("F", "C", len(a["packaging"])), ("G", "D", len(a["cells"])),
              ("H", "E", len(a["watt_hours"])), ("I", "F", len(a["spillability"]))]
    for sheet_col, list_col, n in dv_map:
        dv = DataValidation(type="list",
                            formula1=f"Lists!${list_col}$1:${list_col}${n}",
                            allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{sheet_col}2:{sheet_col}{last_row}")

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ---------------------------------------------------------------------------
# PART 1 — Hazmat
# ---------------------------------------------------------------------------
def _hazmat_tab() -> None:
    st.markdown(
        "<p style='color:var(--muted); font-size:.86rem'>Monitors the "
        "<b>FBA Compliance Dashboard</b>. Live API will connect here once credentials "
        "are added (Settings → Amazon API). For now it uses sample data — or upload the "
        "dashboard export below.</p>", unsafe_allow_html=True)

    up = st.file_uploader("Upload compliance dashboard export (CSV/Excel) — optional",
                          type=["csv", "xlsx"], key="hz_up")
    if up:
        raw = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
        df = pd.DataFrame({
            "asin": get_field(raw, "asin", "").astype(str),
            "sku": get_field(raw, "sku", "").astype(str),
            "title": get_field(raw, "title", "").astype(str),
            "hazmat_status": get_field(raw, "category", "").astype(str)
                if "status" not in [c.lower() for c in raw.columns] else raw[
                    [c for c in raw.columns if c.lower() == "status"][0]].astype(str),
            "fulfilment_channel": get_field(raw, "category", "FBM"),
        })
        src = f"uploaded ({up.name})"
    else:
        df = client().get_hazmat_compliance()
        src = "sample data (upload to override)"
    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)

    df = df.copy()
    df["bucket"] = df["hazmat_status"].map(_hazmat_bucket)
    df["action"] = df["bucket"].map(_ACTION)
    # Reflect any channel decisions already made (persisted) so the column updates.
    overrides = db.get_channel_overrides()
    df["fulfilment_channel"] = df.apply(
        lambda r: overrides.get(r["sku"], r["fulfilment_channel"]), axis=1)

    n_unable = int((df["bucket"] == "unable").sum())
    n_fba = int((df["bucket"] == "fulfillable").sum())
    n_fbm = int((df["bucket"] == "unfulfillable").sum())
    kpi_row([
        {"label": "Unable to classify", "value": str(n_unable), "accent": "amber",
         "sub": "Need exemption sheet"},
        {"label": "FBA Fulfillable", "value": str(n_fba), "accent": "emerald",
         "sub": "Approved → FBA"},
        {"label": "Unfulfillable", "value": str(n_fbm), "accent": "coral",
         "sub": "→ switch to FBM"},
    ])
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # Main table.
    show = df[["asin", "sku", "title", "hazmat_status", "fulfilment_channel", "action"]].copy()
    show["hazmat_status"] = df["bucket"].map(lambda b: _BADGE[b][0])
    styled_table(
        show,
        highlight={"row-danger": lambda r: "Unfulfillable" in r["hazmat_status"],
                   "row-warn": lambda r: "Unable" in r["hazmat_status"],
                   "row-good": lambda r: "Fulfillable" in r["hazmat_status"]},
        badge_cols={"hazmat_status": {v[0]: v for v in _BADGE.values()}})
    export_buttons(df.drop(columns=["bucket"]), "hazmat_compliance")

    # --- Unable to classify → generate exemption sheet --------------------
    st.markdown(section_label("⚠ Unable to classify → generate exemption sheet"),
                unsafe_allow_html=True)
    unable = df[df["bucket"] == "unable"]
    if unable.empty:
        st.caption("No 'unable to classify' items right now.")
    else:
        st.markdown(f"<p style='color:var(--muted)'>{len(unable)} item(s) need a Battery "
                    f"Exemption sheet generated and uploaded.</p>", unsafe_allow_html=True)
        styled_table(unable[["asin", "sku", "title"]])
        xlsx = build_battery_exemption_xlsx(unable)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("📄 Generate Battery Exemption Sheet (.xlsx)", xlsx,
                               file_name="battery_exemption_sheet.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True, key="hz_gen")
        with c2:
            if st.button("⬆ Upload to Amazon (API)", use_container_width=True):
                res = client().upload_hazmat_file(xlsx, "battery_exemption_sheet.xlsx")
                if res.get("status") == "mock_ok":
                    st.info("Mock upload OK. Wire the real compliance API in "
                            "api_client.upload_hazmat_file().")
                for _, r in unable.iterrows():
                    db.add_task(f"Hazmat: submit exemption for {r['title']}",
                                "Generated battery exemption sheet — upload to compliance dashboard.",
                                module="Hazmat & Inactive", priority="high", related_id=r["sku"])
                st.success("Tasks logged for exemption submission.")
        st.caption("The sheet uses Amazon's exact template headers + dropdowns. Fill the "
                   "battery details, then upload (auto-upload connects via API later).")

    # --- Channel switches -------------------------------------------------
    st.markdown(section_label("🔁 Fulfilment channel actions"), unsafe_allow_html=True)
    cc1, cc2 = st.columns(2)
    with cc1:
        fba_items = df[df["bucket"] == "fulfillable"]
        st.markdown(badge(f"{len(fba_items)} approved → FBA", "green"), unsafe_allow_html=True)
        if st.button("Set approved items to FBA", use_container_width=True,
                     disabled=fba_items.empty):
            for _, r in fba_items.iterrows():
                client().set_fulfilment_channel(r["sku"], "FBA")   # API stub
                db.set_channel_override(r["sku"], "FBA")           # persist locally
                db.add_task(f"Switch to FBA: {r['title']}",
                            "Approved as FBA Fulfillable dangerous good.",
                            module="Hazmat & Inactive", priority="medium", related_id=r["sku"])
            st.success(f"Set {len(fba_items)} item(s) to FBA. Reflected in Stock & "
                       f"Inventory views; tasks logged.")
            st.rerun()
    with cc2:
        fbm_items = df[df["bucket"] == "unfulfillable"]
        st.markdown(badge(f"{len(fbm_items)} unfulfillable → FBM", "coral"), unsafe_allow_html=True)
        if st.button("Set unfulfillable items to FBM", use_container_width=True,
                     disabled=fbm_items.empty):
            for _, r in fbm_items.iterrows():
                client().set_fulfilment_channel(r["sku"], "FBM")   # API stub
                db.set_channel_override(r["sku"], "FBM")           # persist locally
                db.add_task(f"Switch to FBM: {r['title']}",
                            "Dangerous good unfulfillable by FBA — move to merchant fulfilment.",
                            module="Hazmat & Inactive", priority="high", related_id=r["sku"])
            st.success(f"Set {len(fbm_items)} item(s) to FBM. Reflected in Stock & "
                       f"Inventory views; tasks logged.")
            st.rerun()


# ---------------------------------------------------------------------------
# PART 2 — Inactive
# ---------------------------------------------------------------------------
def _inactive_tab() -> None:
    up = st.file_uploader("Upload inactive listings export (CSV/Excel) — optional",
                          type=["csv", "xlsx"], key="inact_up")
    if up:
        raw = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
        df = pd.DataFrame({
            "asin": get_field(raw, "asin", ""), "sku": get_field(raw, "sku", ""),
            "title": get_field(raw, "title", ""), "status": "Inactive",
            "reason": get_field(raw, "category", "Unknown"),
            "last_active": get_field(raw, "category", ""),
        })
        src = f"uploaded ({up.name})"
    else:
        df = client().get_inactive_listings()
        src = "sample data (upload to override)"
    st.markdown(badge(f"Source: {src}", "blue"), unsafe_allow_html=True)

    kpi_row([
        {"label": "Inactive listings", "value": str(len(df)), "accent": "coral"},
        {"label": "Out of stock",
         "value": str(int(df["reason"].str.contains("stock", case=False, na=False).sum())),
         "accent": "amber"},
        {"label": "Suppressed",
         "value": str(int(df["reason"].str.contains("suppress", case=False, na=False).sum())),
         "accent": "violet"},
    ])
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    st.markdown(section_label("Inactive Listings"), unsafe_allow_html=True)
    styled_table(df, highlight={"row-danger": lambda r: True})
    export_buttons(df, "inactive_listings")

    if st.button("➕ Add reactivation tasks"):
        for _, r in df.iterrows():
            db.add_task(f"Reactivate: {r['title']}", f"Inactive — {r['reason']}.",
                        module="Hazmat & Inactive", priority="medium", related_id=r["sku"])
        st.success("Reactivation tasks added.")


def render(nav=None) -> None:
    page_header("Hazmat & Inactive",
                "Dangerous-goods compliance and inactive-listing recovery", icon="☣️")
    t1, t2 = st.tabs(["☣️ Hazmat (Dangerous Goods)", "💤 Inactive"])
    with t1:
        _hazmat_tab()
    with t2:
        _inactive_tab()
```

================================================================
FILE: modules/events.py
================================================================
```python
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
```

================================================================
FILE: modules/orders_profit.py
================================================================
```python
"""
modules/orders_profit.py
========================
🧾 Orders & Profit (Module 12).

  * Orders table (id, date, item, qty, status, revenue) with Export.
  * Per-item profit = revenue − cost − ad spend; overall margin.
  * Charts: profit over time, top/bottom profit items (plotly).
"""

from __future__ import annotations
import pandas as pd
import plotly.express as px
import streamlit as st

from core.api_client import client
from core.components import styled_table, export_buttons, kpi_row, page_header
from core.styles import section_label, PALETTE

_DARK = dict(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
             plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=30, b=10))


def render(nav=None) -> None:
    page_header("Orders & Profit", "Every order, every item's margin, at a glance", icon="🧾")
    orders = client().get_orders().copy()
    orders["profit"] = orders["revenue"] - orders["cost"] - orders["ad_spend"]

    rev, profit = orders["revenue"].sum(), orders["profit"].sum()
    margin = (profit / rev * 100) if rev else 0
    kpi_row([
        {"label": "Revenue", "value": f"AED {rev:,.0f}", "accent": "blue"},
        {"label": "Profit", "value": f"AED {profit:,.0f}",
         "accent": "emerald" if profit >= 0 else "coral"},
        {"label": "Margin", "value": f"{margin:.1f}%",
         "accent": "emerald" if margin >= 15 else "amber"},
        {"label": "Orders", "value": str(len(orders)), "accent": "violet"},
    ])

    tabs = st.tabs(["📋 Orders", "💵 Per-item Profit", "📈 Charts"])

    with tabs[0]:
        disp = orders[["order_id", "date", "item", "qty", "status", "revenue"]].copy()
        disp["revenue"] = disp["revenue"].map(lambda v: f"AED {v:,.0f}")
        styled_table(disp, highlight={"row-good": lambda r: r["status"] == "Shipped"})
        export_buttons(orders, "orders")

    with tabs[1]:
        per = orders.groupby("item", as_index=False).agg(
            revenue=("revenue", "sum"), cost=("cost", "sum"),
            ad_spend=("ad_spend", "sum"), profit=("profit", "sum"))
        per["margin_%"] = (per["profit"] / per["revenue"] * 100).round(1)
        per = per.sort_values("profit", ascending=False)
        styled_table(per, highlight={
            "row-good": lambda r: r["profit"] > 0,
            "row-danger": lambda r: r["profit"] <= 0})
        export_buttons(per, "profit_by_item")

    with tabs[2]:
        st.markdown(section_label("Profit Over Time"), unsafe_allow_html=True)
        daily = orders.groupby("date", as_index=False)["profit"].sum()
        fig1 = px.area(daily, x="date", y="profit", markers=True,
                       color_discrete_sequence=[PALETTE["emerald"]])
        fig1.update_layout(**_DARK, height=300)
        st.plotly_chart(fig1, use_container_width=True)

        st.markdown(section_label("Profit by Item"), unsafe_allow_html=True)
        per = orders.groupby("item", as_index=False)["profit"].sum().sort_values("profit")
        fig2 = px.bar(per, x="profit", y="item", orientation="h",
                      color="profit", color_continuous_scale=["#ff5d6c", "#10e0a0"])
        fig2.update_layout(**_DARK, height=340, coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)
```

================================================================
FILE: modules/settings.py
================================================================
```python
"""
modules/settings.py
===================
⚙️ Settings (Module 13).

Persists ALL configuration/secrets in SQLite (never memory):
  * Inventory website base URL + auth
  * connect.oskarme.com base URL + auth (for later)
  * Telegram bot token + chat id
  * SMTP email credentials
  * Anthropic API key (enables the live AI assistant)
  * Amazon API keys (for later)
  * USE_MOCK toggles for Amazon / inventory / oskar connectors
  * Notification channel toggles + per-event triggers
Includes a "Send test notification" button to verify channels.
"""

from __future__ import annotations
import streamlit as st

from core import db, notifier
from core.components import page_header
from core.styles import section_label, badge, alert


def _text(key: str, label: str, password: bool = False, placeholder: str = "") -> None:
    val = db.get_setting(key, "")
    new = st.text_input(label, value=val, type="password" if password else "default",
                        placeholder=placeholder, key=f"set_{key}")
    if new != val:
        db.set_setting(key, new)


def _toggle(key: str, label: str, default: bool = True) -> None:
    cur = db.get_setting(key, "1" if default else "0") == "1"
    new = st.toggle(label, value=cur, key=f"tog_{key}")
    if new != cur:
        db.set_setting(key, "1" if new else "0")


def render(nav=None) -> None:
    page_header("Settings", "Connections, secrets and notification rules (saved to SQLite)",
                icon="⚙️")

    t1, t2, t3, t4 = st.tabs(["🔌 Connections", "🔔 Notifications", "🤖 AI & Amazon", "🧪 Test"])

    with t1:
        st.markdown(section_label("Data source modes"), unsafe_allow_html=True)
        _toggle("use_mock_amazon", "Use MOCK Amazon data (off = live SP-API/Ads)", True)
        _toggle("use_mock_inventory", "Use MOCK inventory website", True)
        _toggle("use_mock_oskar", "Use MOCK enrichment (oskar/scrape)", True)

        st.markdown(section_label("Brand owner defaults (Auto Item Creation)"),
                    unsafe_allow_html=True)
        _toggle("brand_owner_mode",
                "I'm a brand owner — GTIN-exempt (create listings without a barcode)", False)
        _text("default_brand", "Default brand", placeholder="e.g. Powerology")
        _text("default_manufacturer", "Default manufacturer")
        _text("default_country_of_origin", "Default country of origin", placeholder="China")
        _text("default_warranty_line",
              "Warranty / support line (used in the 'What You Get' last bullet)",
              placeholder="24-Hour Customer Service, Lifetime Technical Support and Free 12 + 12 Months Warranty")
        st.caption("These auto-fill on every new item so you don't retype them per arrival.")

        st.markdown(section_label("Inventory website"), unsafe_allow_html=True)
        _text("inventory_base_url", "Base URL", placeholder="https://inventory.mysite.com")
        _text("inventory_auth_token", "Auth token", password=True)

        st.markdown(section_label("connect.oskarme.com (product images)"),
                    unsafe_allow_html=True)
        _text("oskar_base_url", "Base URL", placeholder="https://connect.oskarme.com")
        _text("oskar_token", "Auth token (Bearer JWT)", password=True)
        st.caption("Images are fetched from /api/v1/product/combined-media?item=<SKU>. "
                   "Token = your connect.oskarme.com login JWT (it expires — refresh as needed).")
        osku = st.text_input("Test SKU for image fetch", value="PDLFSTF608WH", key="oskar_test_sku")
        if st.button("🖼️ Test oskar image fetch"):
            if db.get_setting("use_mock_oskar", "1") == "1":
                st.warning("Turn OFF 'Use MOCK enrichment' (top of this tab) to test the real API.")
            else:
                from core import oskar_source
                res = oskar_source.fetch_images_from_media_link("", osku.strip())
                if res["ok"]:
                    st.success(f"✓ {len(res['images'])} image(s) found for {osku.strip()}.")
                    cols = st.columns(min(len(res["images"]), 4))
                    for i, u in enumerate(res["images"][:4]):
                        with cols[i % len(cols)]:
                            st.image(u, width=120)
                else:
                    st.error(f"No images — reason: {res['reason']}")

    with t2:
        st.markdown(section_label("Channels"), unsafe_allow_html=True)
        _toggle("channel_email", "Enable Email (SMTP)", False)
        _toggle("channel_telegram", "Enable Telegram", False)

        st.markdown(section_label("SMTP email"), unsafe_allow_html=True)
        c = st.columns(2)
        with c[0]:
            _text("smtp_host", "SMTP host", placeholder="smtp.gmail.com")
            _text("smtp_user", "SMTP user / from", placeholder="you@gmail.com")
            _text("smtp_to", "Send alerts to", placeholder="you@gmail.com")
        with c[1]:
            _text("smtp_port", "SMTP port", placeholder="587")
            _text("smtp_password", "SMTP password / app key", password=True)

        st.markdown(section_label("Telegram"), unsafe_allow_html=True)
        _text("telegram_bot_token", "Bot token", password=True)
        _text("telegram_chat_id", "Chat id", placeholder="123456789")

        st.markdown(section_label("Trigger which events?"), unsafe_allow_html=True)
        _toggle("notify_on_out_of_stock", "Out of stock detected", True)
        _toggle("notify_on_lost_buybox", "Lost buybox", True)
        _toggle("notify_on_budget", "Campaign over budget", True)
        _toggle("notify_on_daily_tasks", "High-priority daily tasks", True)

    with t3:
        st.markdown(section_label("Anthropic (AI assistant)"), unsafe_allow_html=True)
        _text("anthropic_api_key", "Anthropic API key", password=True,
              placeholder="sk-ant-...")
        has_key = bool(db.get_setting("anthropic_api_key", ""))
        st.markdown(badge("Live Claude enabled" if has_key else "Rule-based fallback active",
                          "green" if has_key else "amber"), unsafe_allow_html=True)

        st.markdown(section_label("OpenAI (A+ Content Studio image generation)"),
                    unsafe_allow_html=True)
        _text("openai_api_key", "OpenAI API key", password=True, placeholder="sk-...")
        _text("image_model", "Image model", placeholder="gpt-image-1")
        has_img = bool(db.get_setting("openai_api_key", ""))
        st.markdown(badge("Image generation enabled" if has_img else "Image generation off",
                          "green" if has_img else "amber"), unsafe_allow_html=True)
        st.caption("Used by A+ Content Studio to render the gpt-image prompts into actual "
                   "images (default model gpt-image-1).")

        st.markdown(section_label("Amazon SP-API (live listing creation)"), unsafe_allow_html=True)
        st.caption("Turn off 'Use MOCK Amazon' (Connections tab) to push real listings.")
        _text("amazon_lwa_client_id", "LWA client id")
        _text("amazon_lwa_client_secret", "LWA client secret", password=True)
        _text("amazon_refresh_token", "Refresh token", password=True)
        _text("amazon_seller_id", "Seller (merchant) id")
        cma, cmb = st.columns(2)
        with cma:
            _text("amazon_marketplace_id", "Marketplace id (UAE = A2VIGQ35RCS4UG)")
        with cmb:
            cur = db.get_setting("amazon_region", "eu") or "eu"
            reg = st.selectbox("SP-API region", ["eu", "na", "fe"],
                               index=["eu", "na", "fe"].index(cur) if cur in ["eu","na","fe"] else 0,
                               help="UAE = eu")
            if reg != cur:
                db.set_setting("amazon_region", reg)
        _text("amazon_ads_profile_id", "Ads profile id (Advertising API)")

        if st.button("🔌 Test SP-API connection"):
            from core import sp_api
            ok, msg = sp_api.test_connection()
            (st.success if ok else st.error)(msg)
            if ok:
                try:
                    pts = sp_api.search_product_types("")
                    st.info(f"Reachable — {len(pts)} product types available in your marketplace.")
                except Exception as e:
                    st.warning(f"Token OK but product-types call failed: {e}")

    with t4:
        st.markdown(section_label("Send a test notification"), unsafe_allow_html=True)
        st.caption("Uses the channels you enabled above with their saved credentials.")
        if st.button("🧪 Send test now"):
            res = notifier.notify_event("daily_tasks", "Test alert from your dashboard",
                                        "✅ If you can read this, notifications work.")
            for ch, ok, msg in res:
                (st.success if ok else st.warning)(f"{ch}: {msg}")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown(section_label("Danger zone"), unsafe_allow_html=True)
        if st.button("🗑️ Clear all tasks"):
            db.clear_tasks()
            st.session_state.pop("tasks_seeded", None)
            st.success("Tasks cleared.")
        if st.button("🗑️ Clear chat history"):
            db.clear_chat()
            st.success("Chat history cleared.")
```

================================================================
FILE: modules/ai_assistant.py
================================================================
```python
"""
modules/ai_assistant.py
=======================
🤖 AI Assistant (Module 14).

Full-page chat grounded in live DB context (tasks, stock, pricing, ads, profit).
Calls Anthropic when a key is set (Settings), else rule-based fallback. History
is persisted in SQLite. Write-actions (create a task, draft a listing, suggest a
price) are exposed as explicit buttons behind a confirmation step so the
assistant never changes live data on its own.

render_sidebar_quickask() powers the persistent sidebar quick-ask box.
"""

from __future__ import annotations
import streamlit as st

from core import db, assistant
from core.components import page_header
from core.styles import section_label, badge, alert


# ---------------------------------------------------------------------------
# Sidebar quick-ask (persistent)
# ---------------------------------------------------------------------------
def render_sidebar_quickask() -> None:
    st.markdown("---")
    st.markdown("#### 🤖 Quick Ask")
    q = st.text_input("Ask the assistant", key="sidebar_quickask",
                      label_visibility="collapsed", placeholder="e.g. what's urgent?")
    if st.button("Ask", key="sidebar_ask_btn", use_container_width=True) and q:
        db.add_chat("user", q)
        db.add_chat("assistant", assistant.answer(q))
        st.session_state["goto_assistant"] = True
        st.rerun()


# ---------------------------------------------------------------------------
# Full page
# ---------------------------------------------------------------------------
def render(nav=None) -> None:
    page_header("AI Assistant", "Grounded in your live data — ask anything about your store",
                icon="🤖")

    has_key = bool(db.get_setting("anthropic_api_key", ""))
    st.markdown(badge("Live Claude (" + assistant.MODEL + ")" if has_key
                      else "Rule-based fallback — add Anthropic key in Settings",
                      "green" if has_key else "amber"), unsafe_allow_html=True)

    # Live context preview.
    with st.expander("📡 Context sent to the assistant", expanded=False):
        ctx = assistant.build_context()
        st.json(ctx)

    # Quick action buttons (write-actions behind confirmation).
    st.markdown(section_label("Quick actions"), unsafe_allow_html=True)
    cols = st.columns(3)
    presets = {
        "🗓️ What should I work on today?": "What should I work on today?",
        "💸 Which items are losing money?": "Which items are losing money?",
        "🏷️ Why did I lose buyboxes?": "Why did I lose buyboxes and what should I do?",
    }
    for col, (label, prompt) in zip(cols, presets.items()):
        if col.button(label, use_container_width=True):
            db.add_chat("user", prompt)
            db.add_chat("assistant", assistant.answer(prompt))
            st.rerun()

    st.markdown("---")

    # Chat history.
    for msg in db.get_chat(50):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Message the assistant…"):
        db.add_chat("user", prompt)
        with st.spinner("Thinking…"):
            reply = assistant.answer(prompt)
        db.add_chat("assistant", reply)
        st.rerun()

    # Confirmed write-action: create a task from the last answer.
    st.markdown(section_label("Turn advice into action (with confirmation)"),
                unsafe_allow_html=True)
    chat = db.get_chat(2)
    last = chat[-1]["content"] if chat else ""
    task_title = st.text_input("Create a task from the assistant's advice",
                               value=(last[:80] if last else ""))
    confirm = st.checkbox("I confirm I want to create this task")
    if st.button("➕ Create task") and task_title and confirm:
        db.add_task(task_title, "Created from AI Assistant.", module="AI Assistant",
                    priority="medium")
        st.success("Task created.")
    elif st.session_state.get("_warn_confirm"):
        st.markdown(alert("Tick the confirmation box first.", kind="amber", icon="⚠️"),
                    unsafe_allow_html=True)
```