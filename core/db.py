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

            CREATE TABLE IF NOT EXISTS restock_queue (
                sku        TEXT PRIMARY KEY,
                title      TEXT,
                asin       TEXT,
                status     TEXT,           -- 'add stock' | 'done'
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS hazmat_status (
                asin       TEXT PRIMARY KEY,
                title      TEXT,
                status     TEXT,           -- raw status (first line)
                bucket     TEXT,           -- fulfillable | unable | unfulfillable | other
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS hazmat_status_changes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                changed_at TEXT,
                asin       TEXT,
                title      TEXT,
                old_status TEXT,
                new_status TEXT
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
    """Pushed items, newest first. Joins the catalog so each row carries the
    confirmed `asin` (empty = Amazon never confirmed it was created) — the
    Submitted/Ready-to-List view uses that to show a truthful created/pending status."""
    with _conn() as c:
        rows = c.execute(
            "SELECT r.*, c.asin AS asin, c.status AS cat_status "
            "FROM ready_to_list r LEFT JOIN catalog c ON c.sku = r.sku "
            "ORDER BY r.created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["images"] = json.loads(d["images"]) if d["images"] else []
        d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
        out.append(d)
    return out


def save_hazmat_statuses(items: list) -> list:
    """Persist the latest hazmat status per ASIN and return the CHANGES vs what was
    stored. `items` = [{asin, title, status, bucket}]. A change is logged when the
    bucket (the meaningful classification) differs from the stored one. Returns
    [{asin, title, old_status, new_status, changed_at}], newest first."""
    changes = []
    now = _now()
    with _conn() as c:
        prev = {r["asin"]: dict(r) for r in
                c.execute("SELECT asin, status, bucket FROM hazmat_status").fetchall()}
        for it in items or []:
            asin = str(it.get("asin") or "").strip()
            if not asin:
                continue
            status = str(it.get("status") or "").strip()
            bucket = str(it.get("bucket") or "").strip()
            title = str(it.get("title") or "")
            old = prev.get(asin)
            if old is not None and old.get("bucket") != bucket:
                c.execute("INSERT INTO hazmat_status_changes"
                          "(changed_at, asin, title, old_status, new_status) VALUES(?,?,?,?,?)",
                          (now, asin, title, old.get("status", ""), status))
                changes.append({"asin": asin, "title": title,
                                "old_status": old.get("status", ""), "new_status": status,
                                "changed_at": now})
            c.execute(
                "INSERT INTO hazmat_status(asin,title,status,bucket,updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(asin) DO UPDATE SET "
                "title=excluded.title, status=excluded.status, bucket=excluded.bucket, "
                "updated_at=excluded.updated_at",
                (asin, title, status, bucket, now))
    return changes


def get_hazmat_changes(limit: int = 200) -> list:
    """Recent hazmat status changes, newest first."""
    with _conn() as c:
        rows = c.execute("SELECT changed_at, asin, title, old_status, new_status "
                         "FROM hazmat_status_changes ORDER BY id DESC LIMIT ?",
                         (int(limit),)).fetchall()
    return [dict(r) for r in rows]


def delete_ready_to_list(skus) -> int:
    """Remove every ready_to_list row for the given SKUs (used to clear entries that
    Amazon never actually created). Returns the number of rows deleted."""
    skus = [s for s in (skus or []) if s]
    if not skus:
        return 0
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM ready_to_list WHERE sku IN (%s)" % ",".join("?" * len(skus)),
            skus)
        return cur.rowcount


def get_created_log() -> list[dict]:
    """Every item pushed to Amazon via Auto Item Creation, newest first, each with
    its creation timestamp (UTC ISO in `created_at`). Joined to the catalog so the
    confirmed ASIN / category come along. One row per push event — re-pushing a SKU
    adds another dated row, which is exactly the creation history the user wants."""
    with _conn() as c:
        rows = c.execute(
            "SELECT r.created_at AS created_at, r.sku AS sku, r.title AS title, "
            "       r.price AS price, c.asin AS asin, c.category AS category "
            "FROM ready_to_list r LEFT JOIN catalog c ON c.sku = r.sku "
            "ORDER BY r.created_at DESC").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Restock queue (new-arrival-badged items that ALREADY exist in the catalogue)
# ---------------------------------------------------------------------------
def add_restock(sku: str, title: str = "", asin: str = "", status: str = "add stock") -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO restock_queue(sku,title,asin,status,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(sku) DO UPDATE SET title=excluded.title, asin=excluded.asin, "
            "updated_at=excluded.updated_at",
            (sku, title, asin, status, _now()))


def get_restock() -> list[dict]:
    with _conn() as c:
        return [dict(r) for r in
                c.execute("SELECT * FROM restock_queue ORDER BY updated_at DESC").fetchall()]


def set_restock_status(sku: str, status: str, asin: str = "") -> None:
    with _conn() as c:
        if asin:
            c.execute("UPDATE restock_queue SET status=?, asin=?, updated_at=? WHERE sku=?",
                      (status, asin, _now(), sku))
        else:
            c.execute("UPDATE restock_queue SET status=?, updated_at=? WHERE sku=?",
                      (status, _now(), sku))


def remove_restock(sku: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM restock_queue WHERE sku=?", (sku,))


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
