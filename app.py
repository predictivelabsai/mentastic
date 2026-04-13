"""
Mentastic — 3-pane chat interface for human performance and readiness.

Left pane:  Auth / About / conversation history
Center:     Chat with Patrick (WebSocket streaming via LangGraph)
Right:      Thinking trace (tool calls, agent activity)

Launch:  python app.py          # port 5001
"""

import os
import uuid as _uuid
import logging
import asyncio
from typing import Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv()

from fasthtml.common import *
from starlette.responses import RedirectResponse

from utils.chat_store import (
    save_conversation, save_message,
    load_conversation_messages, list_conversations,
    delete_conversation,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chat UI Styles (adapted from alpatrade/utils/agui/styles.py)
# ---------------------------------------------------------------------------

CHAT_UI_STYLES = """
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f8fafc;
  --bg-tertiary: #f1f5f9;
  --text-primary: #1e293b;
  --text-secondary: #64748b;
  --text-muted: #94a3b8;
  --border-color: #e2e8f0;
  --border-strong: #cbd5e1;
  --accent: #0d9488;
  --accent-hover: #0f766e;
  --code-bg: #f1f5f9;
  --user-bubble: #0d9488;
  --asst-bubble: #f8fafc;
  --asst-border: #e2e8f0;
}

.chat-container {
  display: flex; flex-direction: column; height: 100%;
  background: var(--bg-primary);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  overflow: hidden;
}

.chat-messages {
  flex: 1; overflow-y: auto; padding: 1rem;
  background: var(--bg-primary);
  display: flex; flex-direction: column; gap: 0.75rem;
}

.chat-container.welcome-active { justify-content: center; }
.chat-container.welcome-active .chat-messages { flex: 0 0 auto; overflow-y: hidden; padding-bottom: 0; }
.chat-container.welcome-active .chat-input { padding-top: 0.75rem; border-top: none; flex: 0 0 auto; }

.chat-message { display: flex; flex-direction: column; max-width: 85%; animation: chat-message-in 0.3s ease-out; }

.chat-message-content {
  padding: 0.75rem 1rem; border-radius: 1.125rem; font-size: 0.875rem;
  line-height: 1.5; word-wrap: break-word; position: relative;
}

.chat-message-content p { margin: 0 0 0.5rem 0; }
.chat-message-content p:last-child { margin-bottom: 0; }
.chat-message-content ul, .chat-message-content ol { margin: 0.5rem 0; padding-left: 1.5rem; }
.chat-message-content li { margin: 0.25rem 0; }
.chat-message-content code { background: var(--code-bg); padding: 0.125rem 0.25rem; border-radius: 0.25rem; font-size: 0.875em; }
.chat-message-content pre { background: var(--bg-secondary); border: 1px solid var(--border-color); padding: 0.75rem; border-radius: 0.5rem; overflow-x: auto; margin: 0.5rem 0; font-size: 0.8rem; }
.chat-message-content pre code { background: none; padding: 0; }
.chat-message-content blockquote { border-left: 3px solid var(--border-color); padding-left: 1rem; margin: 0.5rem 0; color: var(--text-secondary); }
.chat-message-content h1, .chat-message-content h2, .chat-message-content h3 { margin: 0.75rem 0 0.5rem 0; font-weight: 600; }
.chat-message-content strong { color: var(--text-primary); }

@keyframes chat-message-in { from { opacity: 0; transform: translateY(0.5rem); } to { opacity: 1; transform: translateY(0); } }

.chat-user { align-self: flex-end; }
.chat-assistant { align-self: flex-start; }
.chat-user .chat-message-content { background: var(--user-bubble); color: #ffffff; border-bottom-right-radius: 0.375rem; }
.chat-assistant .chat-message-content { background: var(--asst-bubble); color: var(--text-primary); border: 1px solid var(--asst-border); border-bottom-left-radius: 0.375rem; }

.chat-streaming::after { content: '|'; animation: chat-blink 1s infinite; opacity: 0.7; }
@keyframes chat-blink { 0%, 50% { opacity: 0.7; } 51%, 100% { opacity: 0; } }

.chat-input {
  padding: 1.25rem 1.5rem 1.5rem; background: var(--bg-primary);
  border-top: 1px solid var(--border-color); max-width: 800px; margin: 0 auto; width: 100%;
}

.chat-status { min-height: 1rem; padding: 0.25rem 0; color: var(--text-secondary); font-size: 0.8rem; text-align: center; }

.chat-input-form {
  display: grid; grid-template-columns: 1fr auto; gap: 0.5rem; align-items: end; width: 100%;
  background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 1rem; padding: 0.5rem;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.chat-input-form:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1); }

.chat-input-field {
  width: 100%; padding: 0.5rem 0.75rem; border: none; border-radius: 0.5rem;
  background: transparent; color: var(--text-primary); font-family: inherit; font-size: 0.9rem;
  line-height: 1.5; resize: none; min-height: 3.5rem; max-height: 12rem; overflow-y: hidden;
}
.chat-input-field:focus { outline: none; }

.chat-input-button {
  padding: 0.5rem 1rem; background: #0d9488; color: white; border: none; border-radius: 0.625rem;
  font-family: inherit; font-size: 0.875rem; font-weight: 500; cursor: pointer; min-height: 2.25rem; align-self: end;
}
.chat-input-button:hover { background: #0f766e; }
.chat-input-button:disabled { opacity: 0.5; cursor: not-allowed; background: #94a3b8; }
.chat-input-button.sending { animation: pulse-send 1.5s ease-in-out infinite; background: #94a3b8; }
@keyframes pulse-send { 0%, 100% { opacity: 0.5; } 50% { opacity: 0.7; } }

.chat-tool { align-self: center; max-width: 70%; }
.chat-tool .chat-message-content { background: var(--bg-tertiary); color: var(--text-secondary); font-size: 0.8rem; text-align: center; border-radius: 0.75rem; padding: 0.4rem 0.8rem; }

.input-hint { font-size: 0.7rem; color: var(--text-muted); text-align: center; padding-top: 0.25rem; }
.kbd { background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: 3px; padding: 0.1rem 0.35rem; font-family: ui-monospace, monospace; font-size: 0.65rem; }

/* Welcome Screen */
.welcome-hero { display: flex; flex-direction: column; align-items: center; max-width: 640px; margin: 0 auto; padding-top: 2vh; padding-bottom: 2rem; text-align: center; }
.welcome-icon { width: 56px; height: 56px; background: linear-gradient(135deg, #0d9488, #0f766e); border-radius: 16px; display: flex; align-items: center; justify-content: center; margin-bottom: 1.25rem; }
.welcome-title { font-size: 1.5rem; font-weight: 700; background: linear-gradient(135deg, #1e293b, #0d9488); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 0.5rem; }
.welcome-subtitle { font-size: 0.875rem; color: #64748b; margin-bottom: 2rem; }
.welcome-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; width: 100%; }
.welcome-card { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 12px; padding: 1rem; cursor: pointer; text-align: left; transition: all 0.2s; }
.welcome-card:hover { border-color: #5eead4; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(13, 148, 136, 0.1); }
.welcome-card-icon { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 0.5rem; }
.welcome-card-title { font-size: 0.825rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.25rem; }
.welcome-card-desc { font-size: 0.75rem; color: var(--text-secondary); }

.chat-messages { scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent; }
.chat-messages::-webkit-scrollbar { width: 6px; }
.chat-messages::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }

.chat-assistant .chat-message-content { overflow: visible; max-height: none; }

@media (max-width: 768px) {
  .chat-message { max-width: 95%; }
  .welcome-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 480px) {
  .welcome-grid { grid-template-columns: 1fr; }
}
"""

# ---------------------------------------------------------------------------
# Layout CSS — 3-pane grid
# ---------------------------------------------------------------------------

LAYOUT_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f8fafc; color: #1e293b; height: 100vh; overflow: hidden;
}

.app-layout { display: grid; grid-template-columns: 260px 1fr; height: 100vh; transition: grid-template-columns 0.3s ease; }
.app-layout .right-pane { display: none; }
.app-layout.right-open { grid-template-columns: 260px 1fr 380px; }
.app-layout.right-open .right-pane { display: flex; }

/* Left Pane */
.left-pane { background: var(--bg-primary, #fff); border-right: 1px solid var(--border-color, #e2e8f0); display: flex; flex-direction: column; overflow-y: auto; padding: 1rem; gap: 1.25rem; }
.brand { font-size: 1.25rem; font-weight: 700; color: var(--text-primary, #1e293b); text-decoration: none; }
.brand:hover { color: var(--accent, #0d9488); }

.sidebar-header { display: flex; align-items: center; gap: 0.5rem; padding-bottom: 0.75rem; border-bottom: 1px solid #e2e8f0; }
.sidebar-header .brand { border-bottom: none; padding-bottom: 0; }
.chat-badge { font-size: 0.6rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; background: #0d9488; color: white; padding: 0.15rem 0.4rem; border-radius: 0.25rem; }

.new-chat-btn { width: 100%; padding: 0.5rem; background: transparent; border: 1px dashed #cbd5e1; border-radius: 0.5rem; color: #0d9488; font-family: inherit; font-size: 0.8rem; cursor: pointer; transition: all 0.2s; }
.new-chat-btn:hover { background: #f0fdfa; border-color: #5eead4; }

.conv-section { flex: 1; min-height: 100px; max-height: 35vh; overflow-y: auto; display: flex; flex-direction: column; gap: 0.25rem; }
.conv-section h4 { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: #64748b; margin-bottom: 0.25rem; }
.conv-item { display: block; font-size: 0.8rem; padding: 0.5rem 0.6rem; color: #475569; text-decoration: none; border-radius: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: all 0.15s; }
.conv-item:hover { background: #f1f5f9; color: #1e293b; }
.conv-active { background: #f0fdfa; border-left: 2px solid #0d9488; color: #1e293b; }
.conv-empty { font-style: italic; color: #94a3b8; font-size: 0.75rem; padding: 0.5rem; }

/* About expander */
.about-toggle { display: flex; align-items: center; width: 100%; padding: 0.35rem 0.5rem; background: none; border: none; border-radius: 0.375rem; color: #475569; font-family: inherit; font-size: 0.8rem; font-weight: 500; cursor: pointer; text-align: left; transition: all 0.15s; }
.about-toggle:hover { background: #f1f5f9; }
.about-arrow { color: #94a3b8; font-size: 0.65rem; margin-left: auto; transition: transform 0.2s; }
.about-toggle.open .about-arrow { transform: rotate(90deg); }
.about-content { display: none; font-size: 0.75rem; color: #64748b; line-height: 1.5; padding: 0.5rem; border-left: 2px solid #e2e8f0; margin-left: 0.5rem; }
.about-content.open { display: block; }
.about-content a { color: #0d9488; }

/* Auth */
.sidebar-auth { display: flex; flex-direction: column; gap: 0.75rem; }
.sidebar-auth input { width: 100%; padding: 0.5rem 0.6rem; background: var(--bg-secondary, #f8fafc); border: 1px solid var(--border-color, #e2e8f0); border-radius: 0.375rem; color: var(--text-primary, #1e293b); font-family: inherit; font-size: 0.8rem; }
.sidebar-auth input:focus { outline: none; border-color: var(--accent, #0d9488); box-shadow: 0 0 0 2px rgba(13, 148, 136, 0.15); }
.sidebar-auth button { width: 100%; padding: 0.5rem; background: #0d9488; color: white; border: none; border-radius: 0.375rem; font-family: inherit; font-size: 0.8rem; cursor: pointer; }
.sidebar-auth button:hover { background: #0f766e; }
.alt-link { font-size: 0.75rem; color: #64748b; }
.alt-link a { color: #0d9488; }
.error-msg { color: #dc2626; font-size: 0.8rem; }
.success-msg { color: #16a34a; font-size: 0.8rem; }

.sidebar-user-compact { margin-top: auto; border-top: 1px solid #e2e8f0; padding-top: 0.75rem; }
.sidebar-user-compact .name { font-size: 0.8rem; font-weight: 600; color: #1e293b; }
.sidebar-user-compact .email { font-size: 0.7rem; color: #64748b; }
.logout-btn { display: block; padding: 0.35rem 0.5rem; color: #dc2626; text-decoration: none; font-size: 0.85rem; border-radius: 0.375rem; }
.logout-btn:hover { background: rgba(220, 38, 38, 0.08); }

.sidebar-nav { display: flex; flex-direction: column; gap: 0.25rem; padding-top: 0.5rem; border-top: 1px solid #e2e8f0; }
.sidebar-nav a { color: #64748b; text-decoration: none; font-size: 0.8rem; padding: 0.35rem 0.5rem; border-radius: 0.375rem; transition: all 0.15s; }
.sidebar-nav a:hover { background: #f1f5f9; color: #1e293b; }

.sidebar-footer { font-size: 0.7rem; color: #94a3b8; text-align: center; padding-top: 0.5rem; }

/* Center Pane */
.center-pane { display: flex; flex-direction: column; height: 100vh; background: var(--bg-secondary, #f8fafc); overflow: hidden; }
.center-header { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1rem; background: var(--bg-primary, #fff); border-bottom: 1px solid var(--border-color, #e2e8f0); min-height: 3rem; }
.center-header h2 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary, #1e293b); }
.toggle-trace-btn { padding: 0.3rem 0.7rem; background: transparent; color: #64748b; border: 1px solid #e2e8f0; border-radius: 0.375rem; font-family: inherit; font-size: 0.75rem; cursor: pointer; transition: all 0.2s; }
.toggle-trace-btn:hover { background: #f1f5f9; color: #0d9488; border-color: #0d9488; }
.center-chat { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.center-chat > div { flex: 1; display: flex; flex-direction: column; height: 100%; }
.center-chat .chat-container { height: 100%; flex: 1; border: none; border-radius: 0; background: var(--bg-secondary); display: flex; flex-direction: column; }
.center-chat .chat-messages { background: var(--bg-secondary); flex: 1; }
.center-chat .chat-input { background: var(--bg-secondary); border-top: 1px solid var(--border-color); }
.center-chat .chat-input-form { background: var(--bg-primary); border-color: var(--border-color); }
.center-chat .chat-input-form:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(13, 148, 136, 0.1); }

/* Right Pane */
.right-pane { background: var(--bg-primary, #fff); border-left: 1px solid var(--border-color, #e2e8f0); display: flex; flex-direction: column; overflow: hidden; }
.right-header { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color, #e2e8f0); }
.right-header h3 { font-size: 0.85rem; font-weight: 600; color: var(--text-primary, #1e293b); }
.close-trace-btn { background: none; border: none; color: #64748b; cursor: pointer; font-size: 1.1rem; padding: 0.2rem; }
.close-trace-btn:hover { color: #1e293b; }
.right-content { flex: 1; overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; }

/* Trace Entries */
.trace-entry { display: flex; flex-direction: column; gap: 0.25rem; padding: 0.5rem 0.75rem; margin-bottom: 0.5rem; border-left: 3px solid #e2e8f0; border-radius: 0 0.25rem 0.25rem 0; background: #f1f5f9; font-size: 0.8rem; animation: trace-in 0.2s ease-out; }
@keyframes trace-in { from { opacity: 0; transform: translateX(-0.5rem); } to { opacity: 1; transform: translateX(0); } }
.trace-label { color: #94a3b8; font-weight: 500; }
.trace-detail { color: #64748b; font-size: 0.75rem; font-family: ui-monospace, monospace; word-break: break-all; }
.trace-run-start { border-left-color: #0d9488; } .trace-run-start .trace-label { color: #0d9488; }
.trace-run-end { border-left-color: #16a34a; } .trace-run-end .trace-label { color: #16a34a; }
.trace-tool-active { border-left-color: #d97706; } .trace-tool-active .trace-label { color: #d97706; }
.trace-tool-done { border-left-color: #16a34a; } .trace-tool-done .trace-label { color: #16a34a; }
.trace-error { border-left-color: #dc2626; } .trace-error .trace-label { color: #dc2626; }
#trace-content { font-size: 0.8rem; color: #94a3b8; overflow-y: auto; flex: 1; }

/* About page */
.about-page { max-width: 800px; margin: 2rem auto; padding: 2rem; background: #fff; border-radius: 0.75rem; border: 1px solid #e2e8f0; color: #1e293b; }
.about-page h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
.about-page h2 { font-size: 1.1rem; margin-top: 1.5rem; margin-bottom: 0.5rem; color: #0d9488; }
.about-page h3 { font-size: 0.95rem; margin-top: 1rem; margin-bottom: 0.5rem; }
.about-page p { margin-bottom: 0.75rem; line-height: 1.6; color: #475569; }
.about-page ul { margin: 0.5rem 0 1rem 1.5rem; color: #475569; }
.about-page li { margin-bottom: 0.25rem; line-height: 1.5; }
.about-page .tagline { font-size: 1.1rem; font-style: italic; color: #0d9488; margin: 1rem 0; }
.about-page .back-link { display: inline-block; margin-top: 1.5rem; color: #0d9488; text-decoration: none; font-size: 0.85rem; }
.about-page .back-link:hover { text-decoration: underline; }

/* Responsive */
@media (max-width: 768px) {
  .app-layout { grid-template-columns: 1fr !important; }
  .left-pane { display: none; }
  .right-pane { display: none !important; }
}

/* PWA standalone mode */
@media (display-mode: standalone) {
  body { padding-top: env(safe-area-inset-top); }
}
"""

# ---------------------------------------------------------------------------
# JS
# ---------------------------------------------------------------------------

LAYOUT_JS = """
function toggleRightPane() {
    var layout = document.querySelector('.app-layout');
    layout.classList.toggle('right-open');
}

function toggleAbout() {
    var content = document.getElementById('about-content');
    var btn = document.getElementById('about-toggle');
    if (content) content.classList.toggle('open');
    if (btn) btn.classList.toggle('open');
}
"""

_SCROLL_CHAT_JS = "var m=document.getElementById('chat-messages');if(m)m.scrollTop=m.scrollHeight;"
_GUARD_ENABLE_JS = "window._aguiProcessing=true;"
_GUARD_DISABLE_JS = "window._aguiProcessing=false;"


# ---------------------------------------------------------------------------
# SVG Icons for welcome cards
# ---------------------------------------------------------------------------

_ICON_PATRICK = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>'
_ICON_CLIPBOARD = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/></svg>'
_ICON_SEARCH = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>'
_ICON_HEART = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg>'
_ICON_ACTIVITY = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>'
_ICON_CHART = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>'
_ICON_SHIELD = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'


# ---------------------------------------------------------------------------
# UI — renders chat components
# ---------------------------------------------------------------------------

class UI:
    def __init__(self, thread_id: str):
        self.thread_id = thread_id

    def _render_message(self, message: dict):
        role = message.get("role", "assistant")
        cls = "chat-user" if role == "user" else "chat-assistant"
        mid = message.get("message_id", str(_uuid.uuid4()))
        return Div(
            Div(message.get("content", ""), cls="chat-message-content marked"),
            cls=f"chat-message {cls}", id=mid,
        )

    def _render_messages(self, messages: list[dict], oob: bool = False):
        attrs = {"id": "chat-messages", "cls": "chat-messages"}
        if oob:
            attrs["hx_swap_oob"] = "outerHTML"
        return Div(*[self._render_message(m) for m in messages], **attrs)

    def _render_input_form(self, oob_swap=False):
        container_attrs = {"cls": "chat-input", "id": "chat-input-container"}
        if oob_swap:
            container_attrs["hx_swap_oob"] = "outerHTML"
        return Div(
            Div(id="chat-status", cls="chat-status"),
            Form(
                Hidden(name="thread_id", value=self.thread_id),
                Textarea(
                    id="chat-input", name="msg",
                    placeholder="Talk to Patrick about your performance, readiness, or recovery...\nShift+Enter for new line",
                    autofocus=True, autocomplete="off", cls="chat-input-field", rows="2",
                    onkeydown="handleKeyDown(this, event)", oninput="autoResize(this)",
                ),
                Button("Send", type="submit", cls="chat-input-button",
                       onclick="if(window._aguiProcessing){event.preventDefault();return false;}"),
                cls="chat-input-form", id="chat-form", ws_send=True,
            ),
            Div(Span("Enter", cls="kbd"), " to send  ", Span("Shift+Enter", cls="kbd"), " new line", cls="input-hint"),
            **container_attrs,
        )

    def _render_welcome(self):
        cards = [
            ("Readiness Check-In", "Quick self-assessment of your current state", "I'd like to do a readiness check-in", "#3b82f6", _ICON_CLIPBOARD),
            ("Performance Scan", "AI-guided analysis of your performance", "Let's do a performance scan", "#8b5cf6", _ICON_SEARCH),
            ("Recovery Plan", "Personalized recovery recommendations", "Help me create a recovery plan", "#10b981", _ICON_HEART),
            ("Stress & Load", "Assess stress levels and burnout risk", "Analyze my stress and load levels", "#f59e0b", _ICON_ACTIVITY),
            ("Readiness Report", "View your readiness trends over time", "Show me my readiness report", "#ef4444", _ICON_CHART),
            ("Resilience Builder", "Guided exercises for building resilience", "I want to work on resilience building", "#06b6d4", _ICON_SHIELD),
        ]
        card_els = []
        for title, desc, cmd, color, icon_svg in cards:
            card_els.append(
                Div(
                    Div(NotStr(icon_svg), cls="welcome-card-icon", style=f"background:{color}15;color:{color}"),
                    Div(title, cls="welcome-card-title"),
                    Div(desc, cls="welcome-card-desc"),
                    cls="welcome-card",
                    onclick=(
                        f"if(window._aguiProcessing)return;"
                        f"var ta=document.getElementById('chat-input');"
                        f"var fm=document.getElementById('chat-form');"
                        f"if(ta&&fm){{ta.value={repr(cmd)};fm.requestSubmit();}}"
                    ),
                )
            )
        return Div(
            Div(
                Div(NotStr(_ICON_PATRICK), cls="welcome-icon"),
                Div("Patrick", cls="welcome-title"),
                Div("Your AI companion for human performance and readiness", cls="welcome-subtitle"),
                Div(*card_els, cls="welcome-grid"),
                cls="welcome-hero",
            ),
            id="welcome-screen",
        )

    def chat(self):
        return Div(
            Style(CHAT_UI_STYLES),
            Div(self._render_welcome(), id="chat-messages", cls="chat-messages",
                hx_get=f"/agui/messages/{self.thread_id}", hx_trigger="load", hx_swap="outerHTML"),
            self._render_input_form(),
            Script("""
                (function() {
                    function checkWelcome() {
                        var container = document.querySelector('.chat-container');
                        var welcome = document.getElementById('welcome-screen');
                        if (container) {
                            if (welcome) container.classList.add('welcome-active');
                            else container.classList.remove('welcome-active');
                        }
                    }
                    checkWelcome();
                    var container = document.querySelector('.chat-container');
                    if (container) {
                        var observer = new MutationObserver(checkWelcome);
                        observer.observe(container, {childList: true, subtree: true});
                    }
                })();

                function autoResize(textarea) {
                    textarea.style.height = 'auto';
                    var maxH = 12 * 16;
                    var h = Math.min(textarea.scrollHeight, maxH);
                    textarea.style.height = h + 'px';
                    textarea.style.overflowY = textarea.scrollHeight > maxH ? 'auto' : 'hidden';
                }
                function handleKeyDown(textarea, event) {
                    autoResize(textarea);
                    if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        if (window._aguiProcessing) return;
                        var form = textarea.closest('form');
                        if (form && textarea.value.trim()) form.requestSubmit();
                    }
                }
            """),
            Div(id="agui-js", style="display:none"),
            cls="chat-container welcome-active",
            hx_ext="ws", ws_connect=f"/agui/ws/{self.thread_id}",
        )


# ---------------------------------------------------------------------------
# AGUIThread — WebSocket chat thread with LangGraph streaming
# ---------------------------------------------------------------------------

class AGUIThread:
    def __init__(self, thread_id: str, user_id: str = None):
        self.thread_id = thread_id
        self._user_id = user_id
        self._messages: list[dict] = []
        self._connections: Dict[str, Any] = {}
        self.ui = UI(self.thread_id)
        self._loaded = False
        self._agent_instance = None

    def _get_agent(self):
        if not self._agent_instance:
            from utils.agent import create_mentastic_agent
            self._agent_instance = create_mentastic_agent(self._user_id)
        return self._agent_instance

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            self._messages = load_conversation_messages(self.thread_id)
        except Exception:
            pass

    def subscribe(self, connection_id, send):
        self._connections[connection_id] = send

    def unsubscribe(self, connection_id: str):
        self._connections.pop(connection_id, None)

    async def send(self, element):
        for _, send_fn in self._connections.items():
            await send_fn(element)

    async def _send_js(self, js_code: str):
        await self.send(Div(Script(js_code), id="agui-js", hx_swap_oob="innerHTML"))

    async def _handle_message(self, msg: str, session):
        self._ensure_loaded()
        await self._send_js(_GUARD_ENABLE_JS)
        await self._send_js(
            "var w=document.getElementById('welcome-screen');if(w)w.remove();"
            "var c=document.querySelector('.chat-container');if(c)c.classList.remove('welcome-active');"
        )
        await self._handle_ai_run(msg, session)

    async def _handle_ai_run(self, msg: str, session):
        from langchain_core.messages import HumanMessage, AIMessage
        from utils.agent import set_current_user

        if self._user_id:
            set_current_user(self._user_id)

        user_mid = str(_uuid.uuid4())
        asst_mid = str(_uuid.uuid4())
        content_id = f"message-content-{asst_mid}"

        # Save user message
        user_dict = {"role": "user", "content": msg, "message_id": user_mid}
        self._messages.append(user_dict)
        try:
            title = msg[:80] if len(self._messages) == 1 else None
            save_conversation(self.thread_id, user_id=self._user_id, title=title)
        except Exception:
            pass
        try:
            save_message(self.thread_id, "user", msg, user_mid)
        except Exception:
            pass

        # Send user bubble
        await self.send(Div(
            Div(Div(msg, cls="chat-message-content"), cls="chat-message chat-user", id=user_mid),
            id="chat-messages", hx_swap_oob="beforeend",
        ))

        # Clear input
        await self.send(self.ui._render_input_form(oob_swap=True))
        await self._send_js(
            "var b=document.querySelector('.chat-input-button'),t=document.getElementById('chat-input');"
            "if(b){b.disabled=true;b.classList.add('sending')}"
            "if(t){t.disabled=true;t.placeholder='Patrick is thinking...'}"
        )

        # Empty streaming bubble
        await self.send(Div(
            Div(
                Div(
                    Span("", id=content_id),
                    Span("", cls="chat-streaming", id=f"streaming-{asst_mid}"),
                    cls="chat-message-content",
                ),
                cls="chat-message chat-assistant", id=f"message-{asst_mid}",
            ),
            id="chat-messages", hx_swap_oob="beforeend",
        ))

        # Trace: run started
        _open_trace = (
            "var l=document.querySelector('.app-layout');"
            "if(l&&!l.classList.contains('right-open'))l.classList.add('right-open');"
            "setTimeout(function(){var tc=document.getElementById('trace-content');"
            "if(tc)tc.scrollTop=tc.scrollHeight;},100);"
        )
        run_trace_id = str(_uuid.uuid4())
        await self.send(Div(
            Div(Span("Patrick is thinking...", cls="trace-label"), cls="trace-entry trace-run-start", id=f"trace-run-{run_trace_id}"),
            Script(_open_trace),
            id="trace-content", hx_swap_oob="beforeend",
        ))

        # Build LangChain messages
        lc_messages = []
        for m in self._messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            else:
                lc_messages.append(AIMessage(content=content))

        # Stream via astream_events
        full_response = ""
        agent = self._get_agent()
        try:
            async for event in agent.astream_events({"messages": lc_messages}, version="v2"):
                kind = event.get("event", "")

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        token = chunk.content
                        full_response += token
                        await self.send(Span(token, id=content_id, hx_swap_oob="beforeend"))

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    tool_run_id = event.get("run_id", "")[:8]
                    await self.send(Div(
                        Div(Span(f"Tool: {tool_name}", cls="trace-label"), Span("running...", cls="trace-detail"),
                            cls="trace-entry trace-tool-active", id=f"trace-tool-{tool_run_id}"),
                        Script(_open_trace), id="trace-content", hx_swap_oob="beforeend",
                    ))
                    await self.send(Div(
                        Div(Div(f"Running {tool_name}...", cls="chat-message-content"),
                            cls="chat-message chat-tool", id=f"tool-{tool_run_id}"),
                        id="chat-messages", hx_swap_oob="beforeend",
                    ))

                elif kind == "on_tool_end":
                    tool_run_id = event.get("run_id", "")[:8]
                    await self.send(Div(
                        Div("Done", cls="chat-message-content"), cls="chat-message chat-tool",
                        id=f"tool-{tool_run_id}", hx_swap_oob="outerHTML",
                    ))
                    await self.send(Div(
                        Span("Tool complete", cls="trace-label"), cls="trace-entry trace-tool-done",
                        id=f"trace-tool-{tool_run_id}", hx_swap_oob="outerHTML",
                    ))

        except Exception as e:
            error_msg = str(e)
            full_response = f"I encountered an issue: {error_msg}"
            await self.send(Span(f"\n\n**Error:** {error_msg}", id=content_id, hx_swap_oob="beforeend"))
            await self.send(Div(
                Div(Span(f"Error: {error_msg}", cls="trace-label"), cls="trace-entry trace-error"),
                id="trace-content", hx_swap_oob="beforeend",
            ))

        # Remove streaming cursor
        await self.send(Span("", cls="", id=f"streaming-{asst_mid}", hx_swap_oob="outerHTML"))

        # Trace: done
        await self.send(Div(
            Div(Span("Response complete", cls="trace-label"), cls="trace-entry trace-run-end"),
            id="trace-content", hx_swap_oob="beforeend",
        ))

        # Save assistant message and render markdown server-side
        if full_response:
            asst_dict = {"role": "assistant", "content": full_response, "message_id": asst_mid}
            self._messages.append(asst_dict)
            try:
                save_message(self.thread_id, "assistant", full_response, asst_mid)
            except Exception:
                pass

        # Replace streamed raw text with server-rendered markdown HTML
        import markdown as _md
        rendered_html = _md.markdown(full_response or "", extensions=["tables", "fenced_code", "nl2br"])
        await self.send(Div(
            Div(NotStr(rendered_html), cls="chat-message-content"),
            cls="chat-message chat-assistant",
            id=f"message-{asst_mid}",
            hx_swap_oob="outerHTML",
        ))
        await self._send_js(_SCROLL_CHAT_JS)

        # Re-enable input + scroll
        await self._send_js(
            "var b=document.querySelector('.chat-input-button'),t=document.getElementById('chat-input');"
            "if(b){b.disabled=false;b.classList.remove('sending')}"
            "if(t){t.disabled=false;t.placeholder='Talk to Patrick about your performance, readiness, or recovery...\\nShift+Enter for new line';t.focus()}"
            + _GUARD_DISABLE_JS
        )

        # Refresh conversation list
        await self.send(Div(id="conv-list", hx_get="/agui-conv/list",
                            hx_trigger="load", hx_swap="innerHTML", hx_swap_oob="outerHTML"))


# ---------------------------------------------------------------------------
# AGUISetup — wires WebSocket routes into FastHTML app
# ---------------------------------------------------------------------------

class AGUISetup:
    def __init__(self, app):
        self.app = app
        self._threads: Dict[str, AGUIThread] = {}
        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/agui/ui/{thread_id}/chat")
        async def agui_chat_ui(thread_id: str, session):
            session["thread_id"] = thread_id
            return self.thread(thread_id, session).ui.chat()

        @self.app.ws(
            "/agui/ws/{thread_id}",
            conn=self._on_conn,
            disconn=self._on_disconn,
        )
        async def agui_ws(thread_id: str, msg: str, session):
            await self._threads[thread_id]._handle_message(msg, session)

        @self.app.route("/agui/messages/{thread_id}")
        def agui_messages(thread_id: str, session):
            thread = self.thread(thread_id, session)
            thread._ensure_loaded()
            if thread._messages:
                return thread.ui._render_messages(thread._messages)
            return Div(thread.ui._render_welcome(), id="chat-messages", cls="chat-messages")

    def thread(self, thread_id: str, session=None) -> AGUIThread:
        if thread_id not in self._threads:
            user_id = None
            if session and session.get("user"):
                user_id = session["user"].get("user_id")
            self._threads[thread_id] = AGUIThread(thread_id=thread_id, user_id=user_id)
        return self._threads[thread_id]

    def _on_conn(self, ws, send, session):
        tid = session.get("thread_id", "default")
        self.thread(tid, session).subscribe(str(id(ws)), send)

    def _on_disconn(self, ws, session):
        tid = session.get("thread_id", "default")
        if tid in self._threads:
            self._threads[tid].unsubscribe(str(id(ws)))

    def chat(self, thread_id: str):
        return Div(hx_get=f"/agui/ui/{thread_id}/chat", hx_trigger="load", hx_swap="innerHTML")


# ---------------------------------------------------------------------------
# FastHTML App
# ---------------------------------------------------------------------------

from utils.clerk import is_clerk_enabled, verify_clerk_token, get_clerk_user, CLERK_PUBLISHABLE_KEY

# Build headers — include Clerk JS if configured
_hdrs = [
    MarkdownJS(), HighlightJS(langs=['python', 'javascript']),
    Link(rel="manifest", href="/manifest.json"),
    Meta(name="theme-color", content="#0d9488"),
    Meta(name="viewport", content="width=device-width, initial-scale=1, viewport-fit=cover"),
    Meta(name="apple-mobile-web-app-capable", content="yes"),
    Meta(name="apple-mobile-web-app-status-bar-style", content="black-translucent"),
]
if is_clerk_enabled():
    _hdrs.append(Script(src="https://cdn.jsdelivr.net/npm/@clerk/clerk-js@latest/dist/clerk.browser.js"))

app, rt = fast_app(
    exts="ws",
    secret_key=os.getenv("JWT_SECRET", os.urandom(32).hex()),
    hdrs=_hdrs,
    static_path="static",
)

agui = AGUISetup(app)

# Serve manifest.json explicitly (FastHTML may not auto-serve .json)
@rt("/manifest.json")
def manifest():
    import json
    from starlette.responses import Response
    with open("static/manifest.json") as f:
        return Response(f.read(), media_type="application/manifest+json")


# ---------------------------------------------------------------------------
# Landing Page CSS (mentastic.me style — dark teal + green accents)
# ---------------------------------------------------------------------------

LANDING_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #1e293b; }

/* Nav */
.landing-nav { position: fixed; top: 0; left: 0; right: 0; z-index: 100; background: #093c32; padding: 0.75rem 2rem; display: flex; align-items: center; justify-content: space-between; }
.landing-nav .nav-brand { color: #dafef5; font-size: 1.3rem; font-weight: 700; text-decoration: none; letter-spacing: -0.01em; }
.landing-nav .nav-links { display: flex; gap: 1.5rem; align-items: center; }
.landing-nav .nav-links a { color: #dafef5; text-decoration: none; font-size: 0.85rem; opacity: 0.85; transition: opacity 0.2s; }
.landing-nav .nav-links a:hover { opacity: 1; }
.nav-cta { background: #09c209 !important; color: #fff !important; padding: 0.4rem 1rem; border-radius: 6px; font-weight: 600; opacity: 1 !important; }

/* Hero */
.hero { background: linear-gradient(135deg, #093c32 0%, #0d5c47 50%, #0a4a3a 100%); color: #dafef5; padding: 8rem 2rem 5rem; text-align: center; min-height: 80vh; display: flex; flex-direction: column; justify-content: center; align-items: center; }
.hero h1 { font-size: 3rem; font-weight: 800; margin-bottom: 1rem; line-height: 1.15; max-width: 800px; }
.hero h1 span { color: #09c209; }
.hero .subtitle { font-size: 1.15rem; opacity: 0.9; max-width: 650px; margin: 0 auto 2.5rem; line-height: 1.6; }
.hero-buttons { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }
.btn-primary { background: #09c209; color: #fff; padding: 0.75rem 2rem; border-radius: 8px; font-size: 1rem; font-weight: 600; text-decoration: none; border: none; cursor: pointer; transition: background 0.2s; }
.btn-primary:hover { background: #07a507; }
.btn-secondary { background: transparent; color: #dafef5; padding: 0.75rem 2rem; border-radius: 8px; font-size: 1rem; font-weight: 600; text-decoration: none; border: 2px solid rgba(218,254,245,0.3); transition: all 0.2s; }
.btn-secondary:hover { border-color: #dafef5; background: rgba(218,254,245,0.1); }

/* Mini-chat preview */
.mini-chat { max-width: 500px; margin: 3rem auto 0; background: rgba(255,255,255,0.08); border-radius: 16px; padding: 1.5rem; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.12); }
.mini-chat-header { font-size: 0.8rem; color: rgba(218,254,245,0.6); margin-bottom: 0.75rem; text-align: left; }
.mini-chat-msg { background: rgba(255,255,255,0.1); border-radius: 12px; padding: 0.75rem 1rem; margin-bottom: 0.5rem; font-size: 0.9rem; text-align: left; }
.mini-chat-msg.patrick { border-left: 3px solid #09c209; }
.mini-chat-input { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
.mini-chat-input input { flex: 1; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15); border-radius: 8px; padding: 0.6rem 0.75rem; color: #dafef5; font-size: 0.85rem; }
.mini-chat-input input::placeholder { color: rgba(218,254,245,0.4); }
.mini-chat-input button { background: #09c209; color: #fff; border: none; border-radius: 8px; padding: 0.6rem 1rem; font-weight: 600; cursor: pointer; }

/* Sections */
.section { padding: 5rem 2rem; max-width: 1100px; margin: 0 auto; }
.section-dark { background: #f8fafc; }
.section h2 { font-size: 2rem; font-weight: 700; color: #093c32; margin-bottom: 0.75rem; text-align: center; }
.section .section-sub { text-align: center; color: #64748b; font-size: 1.05rem; max-width: 600px; margin: 0 auto 3rem; }

/* How it works */
.steps-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2rem; }
.step { text-align: center; padding: 1.5rem; }
.step-num { width: 48px; height: 48px; background: linear-gradient(135deg, #093c32, #0d5c47); color: #09c209; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.2rem; font-weight: 700; margin: 0 auto 1rem; }
.step h3 { font-size: 1rem; color: #093c32; margin-bottom: 0.5rem; }
.step p { font-size: 0.85rem; color: #64748b; line-height: 1.5; }

/* Features grid */
.features-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; }
.feature-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 1.5rem; transition: all 0.2s; }
.feature-card:hover { border-color: #09c209; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(9,60,50,0.08); }
.feature-icon { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 0.75rem; font-size: 1.2rem; }
.feature-card h3 { font-size: 0.95rem; color: #093c32; margin-bottom: 0.4rem; }
.feature-card p { font-size: 0.8rem; color: #64748b; line-height: 1.5; }

/* Integrations preview */
.integrations-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
.integration-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 1rem; text-align: center; transition: all 0.2s; cursor: default; }
.integration-card:hover { border-color: #09c209; }
.integration-card .int-icon { font-size: 1.5rem; margin-bottom: 0.5rem; }
.integration-card .int-name { font-size: 0.8rem; font-weight: 600; color: #093c32; }
.integration-card .int-status { font-size: 0.7rem; color: #09c209; margin-top: 0.25rem; }

/* Sectors */
.sectors-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; }
.sector-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 2rem 1.5rem; text-align: center; }
.sector-card h3 { font-size: 1rem; color: #093c32; margin-bottom: 0.5rem; }
.sector-card p { font-size: 0.8rem; color: #64748b; line-height: 1.5; }

/* CTA bottom */
.cta-section { background: linear-gradient(135deg, #093c32, #0d5c47); color: #dafef5; padding: 4rem 2rem; text-align: center; }
.cta-section h2 { color: #dafef5; font-size: 2rem; margin-bottom: 0.75rem; }
.cta-section p { opacity: 0.85; margin-bottom: 2rem; font-size: 1.05rem; }

/* Footer */
.landing-footer { background: #062a23; color: rgba(218,254,245,0.6); padding: 2rem; text-align: center; font-size: 0.8rem; }
.landing-footer a { color: #09c209; text-decoration: none; }

/* Auth pages */
.auth-wrapper { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh; padding: 1rem; background: #f8fafc; }
.auth-logo { text-align: center; margin-bottom: 1.5rem; }
.auth-logo .logo-icon { width: 56px; height: 56px; background: linear-gradient(135deg, #093c32, #0d5c47); border-radius: 14px; display: inline-flex; align-items: center; justify-content: center; color: #09c209; font-weight: 800; font-size: 1.4rem; }
.auth-logo .logo-text { font-size: 1.6rem; font-weight: 700; color: #093c32; margin-top: 0.4rem; }
.auth-logo .logo-tagline { font-size: 0.8rem; color: #64748b; }
.auth-card { width: 100%; max-width: 420px; background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 2rem; box-shadow: 0 4px 24px rgba(0,0,0,0.06); }
.auth-card h2 { text-align: center; margin-bottom: 1.5rem; font-size: 1.3rem; color: #093c32; }
.auth-card form { display: flex; flex-direction: column; gap: 0.75rem; }
.auth-card input { width: 100%; padding: 0.6rem 0.75rem; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 0.9rem; font-family: inherit; }
.auth-card input:focus { outline: none; border-color: #09c209; box-shadow: 0 0 0 2px rgba(9,194,9,0.15); }
.auth-card button[type=submit] { width: 100%; padding: 0.65rem; background: #09c209; color: #fff; border: none; border-radius: 8px; font-weight: 600; font-size: 0.9rem; cursor: pointer; font-family: inherit; }
.auth-card button[type=submit]:hover { background: #07a507; }
.auth-card .alt-link { text-align: center; margin-top: 1rem; font-size: 0.85rem; color: #64748b; }
.auth-card .alt-link a { color: #09c209; text-decoration: none; }
.auth-card .error-msg { color: #dc2626; font-size: 0.85rem; text-align: center; background: #fef2f2; padding: 0.5rem; border-radius: 6px; margin-bottom: 0.5rem; }
.auth-card .success-msg { color: #16a34a; font-size: 0.85rem; text-align: center; background: #f0fdf4; padding: 0.5rem; border-radius: 6px; margin-bottom: 0.5rem; }
.auth-footer { text-align: center; margin-top: 2rem; font-size: 0.75rem; color: #94a3b8; }

/* Responsive */
@media (max-width: 768px) {
  .hero h1 { font-size: 2rem; }
  .steps-grid { grid-template-columns: repeat(2, 1fr); }
  .features-grid { grid-template-columns: 1fr; }
  .integrations-grid { grid-template-columns: repeat(2, 1fr); }
  .sectors-grid { grid-template-columns: 1fr; }
  .landing-nav .nav-links a:not(.nav-cta) { display: none; }
}
"""

# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _session_login(session, user: Dict):
    display = user.get("display_name") or ""
    if display.startswith("$2") or not display.strip():
        display = user.get("email", "user").split("@")[0]
    session["user"] = {
        "user_id": str(user.get("user_id") or user.get("clerk_id", "")),
        "email": user.get("email", ""),
        "display_name": display,
    }


def _check_clerk_session(request, session) -> Optional[Dict]:
    """Check for Clerk session token in cookie or header and sync to session."""
    if not is_clerk_enabled():
        return session.get("user")

    # Already synced in this session
    if session.get("user"):
        return session["user"]

    # Check for Clerk __session cookie
    token = request.cookies.get("__session") or ""
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return None

    payload = verify_clerk_token(token)
    if not payload:
        return None

    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        return None

    # Fetch user details from Clerk and sync to our session + DB
    clerk_user = get_clerk_user(clerk_user_id)
    if clerk_user:
        # Ensure user exists in our DB
        from utils.auth import get_user_by_email, create_user
        email = clerk_user["email"]
        if email:
            existing = get_user_by_email(email)
            if not existing:
                existing = create_user(email, password="clerk-managed", display_name=clerk_user["display_name"])
            if existing:
                clerk_user["user_id"] = existing["user_id"]
        _session_login(session, clerk_user)
        return session["user"]

    return None


def _auth_layout(title: str, card_parts: list):
    """Branded auth card layout for login/register pages."""
    return (
        Title(f"{title} — Mentastic"),
        Style(LANDING_CSS),
        Main(
            Div(
                Div(
                    Span("M", cls="logo-icon"),
                    Div("Mentastic", cls="logo-text"),
                    Div("Human Performance & Readiness", cls="logo-tagline"),
                    cls="auth-logo",
                ),
                Div(*card_parts, cls="auth-card"),
                Div("2026 Mentastic. All rights reserved.", cls="auth-footer"),
                cls="auth-wrapper",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Left pane (chat sidebar)
# ---------------------------------------------------------------------------

def _left_pane(session):
    user = session.get("user")

    parts = [
        Div(
            A("Mentastic", href="/", cls="brand"),
            Span("PATRICK", cls="chat-badge"),
            cls="sidebar-header",
        ),
        A("+ New Chat", href="/chat?new=1", cls="new-chat-btn"),
    ]

    parts.append(Div(
        H4("Conversations"),
        Div(id="conv-list", hx_get="/agui-conv/list", hx_trigger="load", hx_swap="innerHTML"),
        cls="conv-section",
    ))

    parts.append(Div(
        A("Integrations", href="/integrations", style="font-size:0.8rem;color:#0d9488;text-decoration:none;"),
        cls="sidebar-nav",
    ))

    if user:
        parts.append(Div(
            Div(user.get("display_name", ""), cls="name"),
            Div(user.get("email", ""), cls="email"),
            cls="sidebar-user-compact",
        ))
        parts.append(Div(
            A("Logout", href="/logout", cls="logout-btn"),
            cls="sidebar-nav",
        ))

    parts.append(Div("Mentastic 2026", cls="sidebar-footer"))
    return Div(*parts, cls="left-pane")


def _right_pane():
    return Div(
        Div(
            H3("Thinking"),
            Button("\u2715", cls="close-trace-btn", onclick="toggleRightPane()"),
            cls="right-header",
        ),
        Div(Div(id="trace-content"), cls="right-content"),
        cls="right-pane",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Landing page (/)
# ---------------------------------------------------------------------------

_INTEGRATIONS = [
    ("Google Fit", "Fitness & activity", "ready"),
    ("Apple Health", "Sleep & vitals", "ready"),
    ("Oura Ring", "Recovery & readiness", "ready"),
    ("Garmin", "Stress & body battery", "ready"),
    ("Google Calendar", "Schedule & load", "ready"),
    ("Spotify", "Mood & listening", "ready"),
    ("Strava", "Exercise patterns", "coming"),
    ("Slack", "Digital overload", "coming"),
]

@rt("/")
def landing(request, session):
    if is_clerk_enabled():
        _check_clerk_session(request, session)
    if session.get("user"):
        return RedirectResponse("/chat", status_code=303)

    return (
        Title("Mentastic — Human Performance & Readiness"),
        Style(LANDING_CSS),

        # Nav
        Nav(
            A("Mentastic", href="/", cls="nav-brand"),
            Div(
                A("About", href="/about"),
                A("Integrations", href="/integrations"),
                A("Sign In", href="/signin"),
                A("Get Started", href="/register", cls="nav-cta"),
                cls="nav-links",
            ),
            cls="landing-nav",
        ),

        # Hero
        Section(
            H1("Build ", Span("power people"), ". Build ", Span("power teams"), "."),
            P("Mentastic turns fragmented human signals into performance clarity. "
              "Through Patrick, your AI companion, understand how fatigue, recovery, stress and "
              "psychological state shape your focus, judgement, readiness and sustainable performance.",
              cls="subtitle"),
            Div(
                A("Get Started Free", href="/register", cls="btn-primary"),
                A("Learn More", href="/about", cls="btn-secondary"),
                cls="hero-buttons",
            ),
            # Anonymous mini-chat — real WebSocket connection to Patrick
            Div(
                Div("Try Patrick — your AI performance companion", cls="mini-chat-header"),
                Div(id="anon-messages"),
                Form(
                    Input(id="anon-input", name="msg", placeholder="Ask Patrick anything...", autocomplete="off"),
                    Hidden(name="thread_id", value=str(_uuid.uuid4())),
                    Button("Send"),
                    cls="mini-chat-input", id="anon-form", ws_send=True,
                ),
                hx_ext="ws", ws_connect=f"/anon-ws/{_uuid.uuid4()}",
                cls="mini-chat",
            ),
            cls="hero",
        ),

        # How it works
        Div(
            Section(
                H2("How It Works"),
                P("From scattered signals to clear, personalised guidance in four steps.", cls="section-sub"),
                Div(
                    Div(Div("1", cls="step-num"), H3("Connect"), P("Link wearables, calendars, and self-reports. Mentastic collects passive and active data without adding friction."), cls="step"),
                    Div(Div("2", cls="step-num"), H3("Understand"), P("AI pattern recognition turns fragmented signals into a coherent picture of your readiness, stress, and recovery state."), cls="step"),
                    Div(Div("3", cls="step-num"), H3("Act"), P("Patrick provides personalised guidance — not generic advice. Concrete actions matched to your current state and patterns."), cls="step"),
                    Div(Div("4", cls="step-num"), H3("Sustain"), P("Continuous monitoring, adaptive follow-ups, and resilience building to sustain strong performance without overload."), cls="step"),
                    cls="steps-grid",
                ),
                cls="section",
            ),
            cls="section-dark",
        ),

        # Patrick's Tools
        Section(
            H2("Patrick's Toolkit"),
            P("Six evidence-based tools for understanding and improving your performance.", cls="section-sub"),
            Div(
                Div(Div("📋", cls="feature-icon", style="background:#eff6ff"), H3("Readiness Check-In"), P("Quick self-assessment of energy, focus, stress, and mood. Track your state over time."), cls="feature-card"),
                Div(Div("🔍", cls="feature-icon", style="background:#f5f3ff"), H3("Performance Scan"), P("AI-guided conversation about your current performance state across six key areas."), cls="feature-card"),
                Div(Div("💚", cls="feature-icon", style="background:#f0fdf4"), H3("Recovery Plan"), P("Personalised physical, cognitive, and emotional recovery recommendations."), cls="feature-card"),
                Div(Div("⚡", cls="feature-icon", style="background:#fffbeb"), H3("Stress & Load Analysis"), P("Assess your demand-to-resource ratio and burnout risk with Green/Yellow/Red framing."), cls="feature-card"),
                Div(Div("📊", cls="feature-icon", style="background:#fef2f2"), H3("Readiness Report"), P("View trends over 7, 14, or 30 days. Detect upward stress or declining energy patterns."), cls="feature-card"),
                Div(Div("🛡", cls="feature-icon", style="background:#ecfeff"), H3("Resilience Builder"), P("30 guided exercises across 6 focus areas: stress, energy, focus, sleep, pressure, general."), cls="feature-card"),
                cls="features-grid",
            ),
            cls="section",
        ),

        # Integrations preview
        Div(
            Section(
                H2("Connect Your Data"),
                P("Mentastic integrates with the tools you already use to build a complete picture.", cls="section-sub"),
                Div(
                    *[Div(
                        Div({"Google Fit":"🏃","Apple Health":"❤️","Oura Ring":"💍","Garmin":"⌚",
                             "Google Calendar":"📅","Spotify":"🎵","Strava":"🚴","Slack":"💬"}.get(name,"📊"), cls="int-icon"),
                        Div(name, cls="int-name"),
                        Div("Ready" if status == "ready" else "Coming soon", cls="int-status"),
                        cls="integration-card",
                    ) for name, desc, status in _INTEGRATIONS],
                    cls="integrations-grid",
                ),
                P(A("View all integrations →", href="/integrations"), style="text-align:center;margin-top:1.5rem;"),
                cls="section",
            ),
            cls="section-dark",
        ),

        # Sectors
        Section(
            H2("Built for High-Responsibility Environments"),
            P("One intelligence system. Multiple sectors. One outcome: stronger people, stronger teams.", cls="section-sub"),
            Div(
                Div(H3("🎖 Military & Defence"), P("Strengthen operational readiness. Detect strain before it becomes failure. Support cognitive readiness and recovery in demanding conditions."), cls="sector-card"),
                Div(H3("🏢 Private Sector"), P("Improve performance quality and reduce hidden productivity loss. Connect workforce wellbeing to measurable performance drivers."), cls="sector-card"),
                Div(H3("🏥 Government & Frontline"), P("Protect human capability where performance quality directly affects safety, service quality and continuity."), cls="sector-card"),
                cls="sectors-grid",
            ),
            cls="section",
        ),

        # CTA
        Div(
            H2("Ready to perform at your best?"),
            P("Start with a free conversation with Patrick. No credit card required."),
            Div(
                A("Create Free Account", href="/register", cls="btn-primary"),
                A("Sign In", href="/signin", cls="btn-secondary"),
                cls="hero-buttons",
            ),
            cls="cta-section",
        ),

        # Footer
        Div(
            "2026 Mentastic — Human Performance & Readiness Platform. ",
            A("About", href="/about"), " · ",
            A("Integrations", href="/integrations"), " · ",
            "Tallinn, Estonia",
            cls="landing-footer",
        ),
    )


# ---------------------------------------------------------------------------
# Anonymous mini-chat WebSocket (landing page)
# ---------------------------------------------------------------------------

_anon_msg_count: Dict[str, int] = {}  # track messages per anon thread
_ANON_MSG_LIMIT = 5  # after this many messages, suggest signup

@app.ws("/anon-ws/{thread_id}")
async def anon_ws(thread_id: str, msg: str, send):
    """Handle anonymous chat on the landing page — limited messages, then nudge to register."""
    from langchain_core.messages import HumanMessage, AIMessage
    from utils.agent import create_mentastic_agent, set_current_user

    count = _anon_msg_count.get(thread_id, 0)
    _anon_msg_count[thread_id] = count + 1

    # Show user message
    await send(Div(
        Div(msg, cls="mini-chat-msg"),
        id="anon-messages", hx_swap_oob="beforeend",
    ))

    # Clear input
    await send(Form(
        Input(id="anon-input", name="msg", placeholder="Ask Patrick anything...", autocomplete="off", autofocus=True),
        Hidden(name="thread_id", value=thread_id),
        Button("Send"),
        cls="mini-chat-input", id="anon-form", ws_send=True, hx_swap_oob="outerHTML",
    ))

    if count >= _ANON_MSG_LIMIT:
        # Nudge to create account
        signup_url = "/register" if not is_clerk_enabled() else "/signin"
        await send(Div(
            Div(NotStr(
                f"I'm really enjoying our conversation! To keep going and save your progress, "
                f'<a href="{signup_url}" style="color:#09c209;font-weight:600;">create a free Mentastic account</a>. '
                f"I'll remember everything we discussed."
            ), cls="mini-chat-msg patrick"),
            id="anon-messages", hx_swap_oob="beforeend",
        ))
        return

    # Stream AI response
    agent = create_mentastic_agent()
    lc_messages = [HumanMessage(content=msg)]
    full_response = ""
    resp_id = str(_uuid.uuid4())[:8]

    # Create empty response div
    await send(Div(
        Div(Span("", id=f"anon-resp-{resp_id}"), cls="mini-chat-msg patrick"),
        id="anon-messages", hx_swap_oob="beforeend",
    ))

    try:
        async for event in agent.astream_events({"messages": lc_messages}, version="v2"):
            if event.get("event") == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    full_response += chunk.content
                    await send(Span(chunk.content, id=f"anon-resp-{resp_id}", hx_swap_oob="beforeend"))
    except Exception as e:
        full_response = f"I had a brief hiccup — try asking again!"
        await send(Span(full_response, id=f"anon-resp-{resp_id}", hx_swap_oob="beforeend"))

    # After response, render markdown
    if full_response:
        import markdown as _md
        rendered = _md.markdown(full_response, extensions=["tables", "fenced_code", "nl2br"])
        await send(Div(
            Div(NotStr(rendered), cls="mini-chat-msg patrick"),
            Div(
                Span("", id=f"anon-resp-{resp_id}"),  # remove raw span
                style="display:none",
            ),
            id="anon-messages", hx_swap_oob="beforeend",
        ))


# ---------------------------------------------------------------------------
# Chat (/chat) — requires auth
# ---------------------------------------------------------------------------

@rt("/chat")
def chat_page(request, session, new: str = "", thread: str = ""):
    # Check Clerk session if enabled
    if is_clerk_enabled():
        _check_clerk_session(request, session)

    if not session.get("user"):
        return RedirectResponse("/signin", status_code=303)

    if new == "1":
        thread_id = str(_uuid.uuid4())
        session["thread_id"] = thread_id
    elif thread:
        thread_id = thread
        session["thread_id"] = thread_id
    else:
        thread_id = session.get("thread_id")
        if not thread_id:
            thread_id = str(_uuid.uuid4())
            session["thread_id"] = thread_id

    return (
        Title("Patrick — Mentastic"),
        Style(LAYOUT_CSS),
        Div(
            _left_pane(session),
            Div(
                Div(
                    H2("Patrick"),
                    Button("Trace", cls="toggle-trace-btn", onclick="toggleRightPane()"),
                    cls="center-header",
                ),
                Div(agui.chat(thread_id), cls="center-chat"),
                cls="center-pane",
            ),
            _right_pane(),
            cls="app-layout",
        ),
        Script(LAYOUT_JS),
    )


@rt("/agui-conv/list")
def conv_list(session):
    current_tid = session.get("thread_id", "")
    user_id = session.get("user", {}).get("user_id") if session.get("user") else None
    try:
        convs = list_conversations(user_id=user_id, limit=20)
    except Exception:
        convs = []

    if not convs:
        return Div(Span("No conversations yet", cls="conv-empty"))

    items = []
    for c in convs:
        tid = c["thread_id"]
        title = c.get("first_msg") or c.get("title") or "New chat"
        if len(title) > 40:
            title = title[:40] + "..."
        cls_name = "conv-item conv-active" if tid == current_tid else "conv-item"
        items.append(A(title, href=f"/chat?thread={tid}", cls=cls_name))

    return Div(*items)


# ---------------------------------------------------------------------------
# Auth routes — standalone pages
# ---------------------------------------------------------------------------

@rt("/signin")
def signin(session, email: str = "", password: str = "", error: str = ""):
    if session.get("user"):
        return RedirectResponse("/chat", status_code=303)

    # If Clerk is enabled, show Clerk sign-in component
    if is_clerk_enabled():
        return (
            Title("Sign In — Mentastic"),
            Style(LANDING_CSS),
            Main(
                Div(
                    Div(
                        Span("M", cls="logo-icon"),
                        Div("Mentastic", cls="logo-text"),
                        Div("Human Performance & Readiness", cls="logo-tagline"),
                        cls="auth-logo",
                    ),
                    Div(id="clerk-signin", style="min-height:400px;display:flex;justify-content:center;"),
                    Div("2026 Mentastic. All rights reserved.", cls="auth-footer"),
                    cls="auth-wrapper",
                ),
                Script(f"""
                    const clerkPubKey = '{CLERK_PUBLISHABLE_KEY}';
                    async function initClerk() {{
                        const clerk = new window.Clerk(clerkPubKey);
                        await clerk.load();
                        if (clerk.user) {{ window.location.href = '/chat'; return; }}
                        clerk.mountSignIn(document.getElementById('clerk-signin'), {{
                            afterSignInUrl: '/chat',
                            afterSignUpUrl: '/chat',
                        }});
                    }}
                    if (window.Clerk) initClerk();
                    else document.addEventListener('DOMContentLoaded', initClerk);
                """),
            ),
        )

    # Fallback: email/password auth
    if email and password:
        from utils.auth import authenticate
        user = authenticate(email, password)
        if not user:
            return RedirectResponse("/signin?error=Invalid+email+or+password", status_code=303)
        _session_login(session, user)
        return RedirectResponse("/chat", status_code=303)

    parts = [H2("Sign In")]
    if error:
        parts.append(P(error, cls="error-msg"))
    parts.append(
        Form(
            Input(type="email", name="email", placeholder="Email", required=True, autofocus=True),
            Input(type="password", name="password", placeholder="Password", required=True),
            Button("Sign In", type="submit"),
            method="post", action="/signin",
        )
    )
    parts.append(Div("Don't have an account? ", A("Create one", href="/register"), cls="alt-link"))
    return _auth_layout("Sign In", parts)


@rt("/register")
def register(session, email: str = "", password: str = "", display_name: str = "", error: str = ""):
    if session.get("user"):
        return RedirectResponse("/chat", status_code=303)

    # If Clerk is enabled, show Clerk sign-up component
    if is_clerk_enabled():
        return (
            Title("Create Account — Mentastic"),
            Style(LANDING_CSS),
            Main(
                Div(
                    Div(
                        Span("M", cls="logo-icon"),
                        Div("Mentastic", cls="logo-text"),
                        Div("Human Performance & Readiness", cls="logo-tagline"),
                        cls="auth-logo",
                    ),
                    Div(id="clerk-signup", style="min-height:400px;display:flex;justify-content:center;"),
                    Div("2026 Mentastic. All rights reserved.", cls="auth-footer"),
                    cls="auth-wrapper",
                ),
                Script(f"""
                    const clerkPubKey = '{CLERK_PUBLISHABLE_KEY}';
                    async function initClerk() {{
                        const clerk = new window.Clerk(clerkPubKey);
                        await clerk.load();
                        if (clerk.user) {{ window.location.href = '/chat'; return; }}
                        clerk.mountSignUp(document.getElementById('clerk-signup'), {{
                            afterSignInUrl: '/chat',
                            afterSignUpUrl: '/chat',
                        }});
                    }}
                    if (window.Clerk) initClerk();
                    else document.addEventListener('DOMContentLoaded', initClerk);
                """),
            ),
        )

    # Fallback: email/password auth
    if email and password:
        if len(password) < 8:
            return RedirectResponse("/register?error=Password+must+be+at+least+8+characters", status_code=303)
        from utils.auth import create_user, get_user_by_email
        existing = get_user_by_email(email)
        if existing:
            return RedirectResponse("/signin?error=Account+already+exists.+Please+sign+in.", status_code=303)
        user = create_user(email=email, password=password, display_name=display_name or None)
        if not user:
            return RedirectResponse("/register?error=Unable+to+create+account", status_code=303)
        _session_login(session, user)
        return RedirectResponse("/chat", status_code=303)

    parts = [H2("Create Account")]
    if error:
        parts.append(P(error, cls="error-msg"))
    parts.append(
        Form(
            Input(type="email", name="email", placeholder="Email", required=True, autofocus=True),
            Input(type="password", name="password", placeholder="Password (min 8 characters)", required=True, minlength="8"),
            Input(type="text", name="display_name", placeholder="Display name (optional)"),
            Button("Create Account", type="submit"),
            method="post", action="/register",
        )
    )
    parts.append(Div("Already have an account? ", A("Sign in", href="/signin"), cls="alt-link"))
    return _auth_layout("Register", parts)


@rt("/logout")
def logout(session):
    session.clear()
    if is_clerk_enabled():
        # Clerk handles sign-out on the client side; just clear server session
        return (
            Title("Logging out..."),
            Style(LANDING_CSS),
            Script(f"""
                async function clerkLogout() {{
                    const clerk = new window.Clerk('{CLERK_PUBLISHABLE_KEY}');
                    await clerk.load();
                    await clerk.signOut();
                    window.location.href = '/';
                }}
                clerkLogout();
            """),
        )
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Integrations page
# ---------------------------------------------------------------------------

_ALL_INTEGRATIONS = [
    ("Google Fit", "🏃", "Fitness & activity tracking", "Steps, calories, workouts, heart rate zones", "ready", "arcade.dev"),
    ("Apple Health", "❤️", "Sleep & vital signs", "Sleep stages, resting HR, HRV, respiratory rate", "ready", "arcade.dev"),
    ("Oura Ring", "💍", "Recovery & readiness", "Sleep score, readiness score, activity, temperature", "ready", "composio.dev"),
    ("Garmin", "⌚", "Stress & body battery", "Stress level, body battery, sleep, pulse ox", "ready", "composio.dev"),
    ("Google Calendar", "📅", "Schedule & cognitive load", "Meeting density, focus time blocks, overload detection", "ready", "arcade.dev"),
    ("Spotify", "🎵", "Mood & listening patterns", "Listening habits, genre patterns, wind-down music", "ready", "arcade.dev"),
    ("Strava", "🚴", "Exercise patterns", "Training load, recovery needs, activity trends", "coming", "composio.dev"),
    ("Slack", "💬", "Digital overload signals", "Message volume, after-hours activity, notification patterns", "coming", "arcade.dev"),
    ("Fitbit", "📱", "Activity & sleep", "Steps, sleep stages, active minutes, heart rate", "coming", "composio.dev"),
    ("Withings", "⚖️", "Body composition", "Weight trends, body composition, blood pressure", "coming", "composio.dev"),
    ("Polar", "🏊", "Training & recovery", "Training load, orthostatic test, sleep tracking", "planned", "composio.dev"),
    ("Whoop", "🔴", "Strain & recovery", "Strain score, recovery score, sleep performance", "planned", "composio.dev"),
]

@rt("/integrations")
def integrations(session):
    ready = [i for i in _ALL_INTEGRATIONS if i[4] == "ready"]
    coming = [i for i in _ALL_INTEGRATIONS if i[4] == "coming"]
    planned = [i for i in _ALL_INTEGRATIONS if i[4] == "planned"]

    def _card(name, icon, subtitle, detail, status, provider):
        badge_color = {"ready": "#09c209", "coming": "#f59e0b", "planned": "#94a3b8"}[status]
        badge_text = {"ready": "Ready", "coming": "Coming Soon", "planned": "Planned"}[status]
        return Div(
            Div(icon, cls="int-icon", style="font-size:2rem;margin-bottom:0.5rem;"),
            Div(name, style="font-weight:600;color:#093c32;font-size:0.95rem;"),
            Div(subtitle, style="font-size:0.8rem;color:#64748b;margin:0.25rem 0;"),
            Div(detail, style="font-size:0.75rem;color:#94a3b8;line-height:1.4;margin:0.5rem 0;"),
            Div(
                Span(badge_text, style=f"background:{badge_color}15;color:{badge_color};padding:0.2rem 0.5rem;border-radius:4px;font-size:0.7rem;font-weight:600;"),
                Span(f"via {provider}", style="font-size:0.65rem;color:#94a3b8;margin-left:0.5rem;"),
            ),
            style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:1.25rem;",
        )

    return (
        Title("Integrations — Mentastic"),
        Style(LANDING_CSS),
        Nav(
            A("Mentastic", href="/", cls="nav-brand"),
            Div(
                A("About", href="/about"),
                A("Chat", href="/chat"),
                A("Sign In" if not session.get("user") else "Chat", href="/signin" if not session.get("user") else "/chat", cls="nav-cta"),
                cls="nav-links",
            ),
            cls="landing-nav",
        ),
        Div(
            Section(
                H2("Data Integrations"),
                P("Mentastic connects to the tools you already use — wearables, calendars, social platforms — "
                  "to build a complete picture of your readiness and performance without added friction.", cls="section-sub"),
                P("Integrations are powered by ", A("arcade.dev", href="https://arcade.dev"), " and ",
                  A("composio.dev", href="https://composio.dev"), " for secure, privacy-aware data connections.",
                  style="text-align:center;color:#64748b;font-size:0.9rem;margin-bottom:2rem;"),

                H3("Ready", style="color:#09c209;margin-bottom:1rem;"),
                Div(*[_card(*i) for i in ready], style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:2.5rem;"),

                H3("Coming Soon", style="color:#f59e0b;margin-bottom:1rem;"),
                Div(*[_card(*i) for i in coming], style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:2.5rem;"),

                H3("Planned", style="color:#94a3b8;margin-bottom:1rem;"),
                Div(*[_card(*i) for i in planned], style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:2rem;"),

                P("Have a data source you'd like us to support? ", A("Let us know", href="mailto:hello@mentastic.me"),
                  style="text-align:center;color:#64748b;font-size:0.9rem;margin-top:2rem;"),
                cls="section",
            ),
            style="padding-top:4rem;min-height:100vh;background:#f8fafc;",
        ),
        Div("2026 Mentastic", cls="landing-footer"),
    )


# ---------------------------------------------------------------------------
# About page
# ---------------------------------------------------------------------------

@rt("/about")
def about(session):
    return (
        Title("About — Mentastic"),
        Style(LANDING_CSS),
        Nav(
            A("Mentastic", href="/", cls="nav-brand"),
            Div(
                A("Integrations", href="/integrations"),
                A("Chat", href="/chat"),
                A("Sign In" if not session.get("user") else "Chat", href="/signin" if not session.get("user") else "/chat", cls="nav-cta"),
                cls="nav-links",
            ),
            cls="landing-nav",
        ),
        Div(
            Section(
                H1("Mentastic", style="color:#093c32;"),
                P("From fragmented signals to performance clarity.", style="font-size:1.15rem;color:#09c209;font-style:italic;margin:1rem 0 2rem;"),

                H2("What is Mentastic?", style="text-align:left;"),
                P("Mentastic is a human performance intelligence system that turns fragmented data into actionable clarity. "
                  "By combining passive and active inputs — including wearables, sleep, mood, behaviour patterns, digital habits, "
                  "self-reports, psychometrics and AI-guided dialogue — Mentastic helps individuals and organisations understand "
                  "readiness, detect early strain, and improve resilience and performance over time."),
                P("Built as a modular toolbox, Mentastic can be implemented across defence, workplaces, healthcare, "
                  "education and other high-responsibility environments."),

                H2("How It Works", style="text-align:left;"),
                P("Mentastic works as a modular toolbox and intelligence layer for human performance and readiness. "
                  "It combines passive data, self-report, assessments and guided interaction into an adaptive view of the "
                  "user's current state. Through Patrick, our AI companion, it helps users understand what is affecting "
                  "readiness and performance, and what to do next."),

                H2("Core Promise", style="text-align:left;"),
                P("Mentastic helps people and organisations stay ready, perform well under pressure, "
                  "and sustain strong results without drifting into overload.", style="font-weight:600;"),
                P("It does this by turning fragmented human signals into clear, personalised insight that "
                  "supports better decisions, earlier action and more effective support over time."),

                H2("Value Propositions", style="text-align:left;"),
                H3("Military & Defence", style="color:#093c32;"),
                P("Mentastic helps defence organisations strengthen operational readiness by turning human signals "
                  "into early insight on fatigue, stress load, recovery and resilience."),
                Ul(
                    Li("Better readiness visibility without adding major friction"),
                    Li("Earlier detection of overload, fatigue and performance decline"),
                    Li("Stronger resilience and recovery in high-pressure roles"),
                    Li("Privacy-aware intelligence for individuals and command-level structures"),
                ),
                H3("Private Sector Employers", style="color:#093c32;"),
                P("Mentastic helps employers improve performance quality, reduce hidden productivity loss, "
                  "and build more resilient teams through personalised, data-driven insight."),
                Ul(
                    Li("Better performance without framing fatigue as personal weakness"),
                    Li("Early signals before disengagement, overload or absence increase"),
                    Li("Stronger employee retention through smarter support"),
                    Li("Connects workforce wellbeing to measurable performance drivers"),
                ),
                H3("Government, Hospitals & Frontline", style="color:#093c32;"),
                P("Mentastic helps public-sector and frontline organisations protect human capability "
                  "in environments where performance quality directly affects safety and continuity."),
                Ul(
                    Li("Better support for staff in emotionally demanding environments"),
                    Li("Reduced hidden strain affecting quality of service"),
                    Li("Continuous insight, not occasional survey snapshots"),
                    Li("Useful across prevention, early intervention and ongoing support"),
                ),

                H2("What Makes Mentastic Different", style="text-align:left;"),
                Ul(
                    Li("Integrates wearables, mood, sleep, routines, digital habits, behavioural patterns, self-reports and conversation into one intelligence model"),
                    Li("Combines passive + active data in one system"),
                    Li("Personalised guidance, not generic advice"),
                    Li("Connects wellbeing with readiness, focus, resilience and sustainable performance"),
                    Li("Chat + psychological tools + continuous modelling"),
                    Li("Privacy-aware organisational value"),
                    Li("Modular toolbox architecture across sectors"),
                ),
                P("One intelligence system. Multiple tools. Multiple sectors. "
                  "One outcome: stronger people, stronger teams.",
                  style="font-style:italic;color:#09c209;margin-top:1.5rem;"),

                Div(
                    A("← Back to Home", href="/", style="color:#09c209;text-decoration:none;font-size:0.9rem;"),
                    style="margin-top:2rem;",
                ),
                cls="section", style="max-width:800px;",
            ),
            style="padding-top:4rem;min-height:100vh;background:#f8fafc;",
        ),
        Div("2026 Mentastic — Tallinn, Estonia", cls="landing-footer"),
    )


serve(port=int(os.getenv("PORT", "5010")))
