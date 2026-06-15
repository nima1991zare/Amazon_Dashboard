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
