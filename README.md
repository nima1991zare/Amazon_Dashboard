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
