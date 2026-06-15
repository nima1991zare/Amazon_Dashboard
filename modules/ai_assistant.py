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
    st.markdown(badge("Live Claude (" + assistant.model() + ")" if has_key
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
