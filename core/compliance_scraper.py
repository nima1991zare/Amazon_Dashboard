"""
core/compliance_scraper.py
==========================
Browser auto-pull of the FBA Compliance Dashboard (Amazon exposes NO SP-API for it).

Uses Playwright with a PERSISTENT profile so you sign in to Seller Central ONCE; after
that the dashboard data is pulled automatically. Prefers your installed Chrome
(channel="chrome") so no Chromium download is needed; falls back to Edge, then to a
bundled Chromium. Playwright runs in a SUBPROCESS so it never clashes with Streamlit's
event loop.

  available()  -> is Playwright importable?
  login()      -> opens a VISIBLE browser to Seller Central so you can sign in (saved)
  fetch()      -> opens the compliance dashboard, captures its data feed, returns rows

Data extraction is two-pronged and selector-agnostic:
  1) capture JSON the dashboard's own XHRs return (robust to UI changes), pick the
     largest list of dicts that has an ASIN-like key;
  2) failing that, scrape any HTML <table> on the page.
"""
from __future__ import annotations
import os
import sys
import json
import subprocess

COMPLIANCE_URL = "https://sellercentral.amazon.ae/fba/compliance-dashboard/index.html"
SIGNIN_HOME = "https://sellercentral.amazon.ae/"
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
PROFILE_DIR = os.path.join(_ROOT, "data", ".sc_profile")


def available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False


def login() -> tuple[bool, str]:
    """Open a visible browser so the user signs in to Seller Central (session persists
    in PROFILE_DIR). Non-blocking — returns as soon as the browser is launched."""
    if not available():
        return False, "Playwright not installed"
    try:
        subprocess.Popen([sys.executable, "-m", "core.compliance_scraper", "login"], cwd=_ROOT)
        return True, "Browser opening — sign in to Seller Central, then close the window."
    except Exception as e:
        return False, str(e)


def upload(asin: str, file_path: str) -> tuple[bool, str]:
    """Open a VISIBLE browser on the compliance dashboard's Upload-document modal with
    the ASIN typed and the file attached, so the seller picks the language and clicks
    Upload themselves (the final submit stays human — safest for a live account).
    Non-blocking."""
    if not available():
        return False, "Playwright not installed"
    if not os.path.exists(file_path):
        return False, "file to upload not found"
    try:
        subprocess.Popen([sys.executable, "-m", "core.compliance_scraper", "upload",
                          asin, file_path], cwd=_ROOT)
        return True, ("Amazon is opening — it fills the ASIN + file, selects **English**, "
                      "and clicks **Upload** automatically. Watch the window to confirm, "
                      "then come back and **Pull** to refresh the table.")
    except Exception as e:
        return False, str(e)


def fetch(timeout: int = 300) -> dict:
    """Run the scraper subprocess and return {'ok', 'rows', 'reason'}."""
    if not available():
        return {"ok": False, "rows": [], "reason": "Playwright not installed"}
    try:
        p = subprocess.run([sys.executable, "-m", "core.compliance_scraper", "fetch"],
                           cwd=_ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "rows": [], "reason": f"timed out after {timeout}s"}
    out = (p.stdout or "").strip()
    for line in reversed(out.splitlines()):          # the worker prints JSON on its last line
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                break
    return {"ok": False, "rows": [], "reason": (p.stderr or out or "no output")[:300]}


# ---------------------------------------------------------------------------
# Worker (runs in the subprocess) — Playwright only imported here.
# ---------------------------------------------------------------------------
def _launch(pw, headless: bool):
    """Persistent context using installed Chrome → Edge → bundled Chromium."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    errs = []
    for channel in ("chrome", "msedge", None):
        try:
            kw = {"headless": headless}
            if channel:
                kw["channel"] = channel
            return pw.chromium.launch_persistent_context(PROFILE_DIR, **kw)
        except Exception as e:
            errs.append(f"{channel or 'chromium'}: {str(e).splitlines()[0][:80]}")
    raise RuntimeError("no browser could launch (" + " | ".join(errs) + ")")


def _rows_from_json(data) -> list:
    """Largest list-of-dicts anywhere in `data` whose dicts carry an ASIN-like key."""
    best = []

    def walk(o):
        nonlocal best
        if isinstance(o, list) and o and all(isinstance(x, dict) for x in o):
            keys = " ".join(set().union(*[set(map(str, d.keys())) for d in o[:5]])).lower()
            if "asin" in keys and len(o) > len(best):
                best = o
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return [dict(d) for d in best]


def _scrape_dom(page) -> list:
    """Fallback: read the first HTML table with a header into list-of-dicts."""
    try:
        return page.evaluate(
            """() => {
                const t = document.querySelector('table');
                if (!t) return [];
                const heads = [...t.querySelectorAll('thead th, tr:first-child th, tr:first-child td')]
                    .map(e => e.innerText.trim());
                const rows = [...t.querySelectorAll('tbody tr')];
                return rows.map(r => {
                    const cells = [...r.querySelectorAll('td')].map(e => e.innerText.trim());
                    const o = {};
                    cells.forEach((c, i) => o[heads[i] || ('col' + i)] = c);
                    return o;
                });
            }""")
    except Exception:
        return []


def _run_login():
    """Open a visible browser for sign-in. Needs a real desktop session; best-effort."""
    try:
        import time
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            ctx = _launch(pw, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(SIGNIN_HOME, timeout=60000)
            except Exception:
                pass
            deadline = time.time() + 360          # up to 6 min to sign in, then exit
            while time.time() < deadline and ctx.pages:
                time.sleep(2)
            try:
                ctx.close()
            except Exception:
                pass
    except Exception:
        pass                                       # login is fire-and-forget (no output read)


def _scrape_all_pages(page, max_pages: int = 80, keep_last: int = 10) -> list:
    """Walk the dashboard's prev/next pager forward, scraping each page's table, then
    return the LAST `keep_last` pages' rows (0 = all pages). Next = the <li class='nav'>
    holding a chevron-right kat-icon; while more pages exist its class is
    'pagination-has-more' (→ 'pagination-end' on the last page). Dedupes by ASIN."""
    chunks = []                                    # one list of rows per page, in order
    for _ in range(max_pages):
        page.wait_for_timeout(600)
        chunks.append(_scrape_dom(page))
        has_more = page.evaluate(
            "() => { const i=document.querySelector('li.nav kat-icon[name=chevron-right]');"
            " return !!(i && (i.className||'').includes('pagination-has-more')); }")
        if not has_more:
            break
        cur = page.evaluate("() => { const p=document.querySelector('li.page');"
                            " return p ? p.innerText.trim() : ''; }")
        page.evaluate(
            "() => { const navs=[...document.querySelectorAll('li.nav')];"
            " const nx=navs.find(n=>n.querySelector('kat-icon[name=chevron-right]'));"
            " if (nx) nx.click(); }")
        try:                                       # wait for the page number to advance
            page.wait_for_function(
                "(prev)=>{ const p=document.querySelector('li.page');"
                " return p && p.innerText.trim()!==prev; }", arg=cur, timeout=10000)
        except Exception:
            pass

    kept = chunks[-keep_last:] if keep_last else chunks
    seen, rows = set(), []
    for chunk in kept:
        for r in chunk:
            key = str(r.get("ASIN") or r.get("asin") or "").strip() or json.dumps(r, sort_keys=True)
            if key not in seen:
                seen.add(key)
                rows.append(r)
    return rows


def _fetch_once(headless: bool) -> dict:
    from playwright.sync_api import sync_playwright
    captured = []

    def on_response(resp):
        try:
            if "application/json" in (resp.headers or {}).get("content-type", ""):
                r = _rows_from_json(resp.json())
                if r:
                    captured.append(r)
        except Exception:
            pass

    with sync_playwright() as pw:
        ctx = _launch(pw, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("response", on_response)
        try:
            page.goto(COMPLIANCE_URL, wait_until="networkidle", timeout=90000)
        except Exception:
            pass
        url = page.url
        if "signin" in url or "/ap/" in url:
            try:
                ctx.close()
            except Exception:
                pass
            return {"ok": False, "rows": [],
                    "reason": "not signed in — click 'Log in to Seller Central' first"}
        page.wait_for_timeout(4000)
        rows = _scrape_all_pages(page)            # paginate every page
        if not rows and captured:                 # fallback to the XHR JSON if the table didn't parse
            rows = max(captured, key=len)
        try:
            ctx.close()
        except Exception:
            pass
    return {"ok": bool(rows), "rows": rows, "pages_msg": f"{len(rows)} items across pages",
            "reason": "" if rows else "page loaded but no item rows found"}


def _run_fetch():
    """Try VISIBLE first (real desktop, keeps the login session, dodges bot-blocks);
    fall back to HEADLESS if there's no display. Always prints clean JSON, never a traceback."""
    last_err = None
    for headless in (False, True):
        try:
            print(json.dumps(_fetch_once(headless)))
            return
        except Exception as e:
            last_err = str(e).splitlines()[0][:200]
    print(json.dumps({"ok": False, "rows": [], "reason": f"browser launch failed — {last_err}"}))


def _select_english(page):
    """Set every language kat-dropdown to English (value 'EN'). Tries the JS value
    setter and clicking the English option (covers Katal's shadow-DOM rendering)."""
    try:
        page.evaluate("() => { document.querySelectorAll('kat-dropdown').forEach(dd => {"
                      " try { dd.value='EN'; dd.setAttribute('value','EN');"
                      " dd.dispatchEvent(new Event('change',{bubbles:true})); } catch(e){} }); }")
    except Exception:
        pass
    try:
        dds = page.locator("kat-dropdown")
        for idx in range(dds.count()):
            try:
                dds.nth(idx).click(timeout=3000)
                page.wait_for_timeout(500)
                opt = page.locator('kat-option[value="EN"]')
                if opt.count():
                    opt.first.click(timeout=2000)
                    page.wait_for_timeout(300)
            except Exception:
                pass
    except Exception:
        pass


def _run_upload(asin: str, file_path: str):
    """Visible browser: open the Upload-document modal, type the ASIN, attach the file,
    select English, and click Upload. Window stays open so the seller sees the result."""
    try:
        import time
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            ctx = _launch(pw, headless=False)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(COMPLIANCE_URL, wait_until="networkidle", timeout=90000)
            except Exception:
                pass
            page.wait_for_timeout(4000)
            page.evaluate("() => { const b=[...document.querySelectorAll('kat-button')]"
                          ".find(x=>/upload document/i.test((x.getAttribute('label')||x.innerText||'')));"
                          " if(b)b.click(); }")
            page.wait_for_timeout(2500)
            try:                                            # type the ASIN
                page.locator('kat-input[placeholder*="Specify ASIN"]').click(timeout=6000)
                page.keyboard.type(str(asin))
            except Exception:
                pass
            try:                                            # attach the reviewed sheet
                page.set_input_files('input[name=uploadFile]', file_path, timeout=8000)
            except Exception:
                pass
            _select_english(page)                           # always English
            page.wait_for_timeout(600)
            try:                                            # click the 'Upload' submit button
                page.evaluate("() => { const b=[...document.querySelectorAll('kat-button')]"
                              ".find(x=>{const t=(x.getAttribute('label')||x.innerText||'')"
                              ".trim().toLowerCase(); return t==='upload';}); if(b)b.click(); }")
            except Exception:
                pass
            deadline = time.time() + 240                    # keep open ~4 min to verify result
            while time.time() < deadline and ctx.pages:
                time.sleep(2)
            try:
                ctx.close()
            except Exception:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if mode == "login":
        _run_login()
    elif mode == "upload":
        _run_upload(sys.argv[2] if len(sys.argv) > 2 else "",
                    sys.argv[3] if len(sys.argv) > 3 else "")
    else:
        _run_fetch()
