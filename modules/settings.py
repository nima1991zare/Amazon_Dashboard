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
        st.markdown(section_label("Anthropic (Claude — powers all AI features)"),
                    unsafe_allow_html=True)
        _text("anthropic_api_key", "Anthropic API key", password=True,
              placeholder="sk-ant-...")
        has_key = bool(db.get_setting("anthropic_api_key", ""))
        st.markdown(badge("Live Claude enabled" if has_key else "Rule-based fallback active",
                          "green" if has_key else "amber"), unsafe_allow_html=True)
        _MODELS = ["claude-opus-4-8", "claude-opus-4-6",
                   "claude-sonnet-4-6", "claude-sonnet-4-5"]
        cur_m = db.get_setting("anthropic_model", "") or "claude-opus-4-8"
        mdl = st.selectbox(
            "Claude model (used for listing copy, A+ content, assistant, optimization)",
            _MODELS, index=_MODELS.index(cur_m) if cur_m in _MODELS else 0,
            help="Opus 4.8 = most capable (best listing copy). Sonnet = faster/cheaper "
                 "for bulk runs.")
        if mdl != cur_m:
            db.set_setting("anthropic_model", mdl)
        st.caption("Claude writes titles, bullets, descriptions & keywords during Auto Item "
                   "Creation when a key is set — far better than the rule-based fallback.")

        st.markdown(section_label("OpenAI (A+ Content Studio image generation)"),
                    unsafe_allow_html=True)
        _text("openai_api_key", "OpenAI API key", password=True, placeholder="sk-...")
        _IMG_MODELS = ["gpt-image-2", "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini"]
        cur_im = db.get_setting("image_model", "") or "gpt-image-2"
        imdl = st.selectbox("Image model", _IMG_MODELS,
                            index=_IMG_MODELS.index(cur_im) if cur_im in _IMG_MODELS else 0,
                            help="gpt-image-2 = newest/best. mini = cheaper/faster for drafts.")
        if imdl != cur_im:
            db.set_setting("image_model", imdl)
        has_img = bool(db.get_setting("openai_api_key", ""))
        st.markdown(badge(f"Image generation enabled ({imdl})" if has_img
                          else "Image generation off",
                          "green" if has_img else "amber"), unsafe_allow_html=True)
        st.caption("Used by A+ Content Studio to render prompts into actual images.")

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
