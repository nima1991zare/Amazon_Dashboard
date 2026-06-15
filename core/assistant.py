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

# Default to the latest, most capable Claude model. Overridable in Settings
# (AI & Amazon → Claude model) and read fresh on every call so a change in
# Settings takes effect without a restart.
DEFAULT_MODEL = "claude-opus-4-8"


def model() -> str:
    return db.get_setting("anthropic_model", "") or DEFAULT_MODEL


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
            model=model(), max_tokens=max_tokens, system=system_prompt,
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
        model=model(), max_tokens=900, system=system,
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
