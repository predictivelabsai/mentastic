# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Mentastic is a human performance and readiness platform. A single-process FastHTML app with a 3-pane chat UI, WebSocket streaming via LangGraph, and PostgreSQL persistence. The AI companion is called **Patrick**.

## Commands

```bash
# Run the app (port 5010)
.venv/bin/python app.py

# Run test suite (19 tests, no app needed)
.venv/bin/python tests/test_suite.py

# Capture screenshots (app must be running on :5010)
.venv/bin/python tests/capture_guide.py

# Capture demo video + GIF (app must be running on :5010)
.venv/bin/python tests/capture_video.py

# Run SQL schema
psql $DB_URL -f sql/01_create_schema.sql

# Docker
docker compose up --build
```

## Architecture

Everything runs in one process. No frontend build step — pure server-rendered HTML via FastHTML + HTMX.

### app.py (~1100 lines, monolith)

Contains three class layers for the chat system, all CSS, all routes:

- **`UI`** — Renders HTML components: messages, input form, 6 welcome cards. Stateless.
- **`AGUIThread`** — One per conversation. Holds in-memory message list, WebSocket subscriber set, and a lazy-loaded LangGraph agent. The `_handle_ai_run()` method streams `agent.astream_events(version="v2")` and pushes tokens to the browser via `hx_swap_oob="beforeend"` on a Span.
- **`AGUISetup`** — Singleton wired to the FastHTML app. Registers the WS route (`/agui/ws/{thread_id}`), manages an in-memory `_threads` dict, and handles connect/disconnect lifecycle.

The chat container div must have `hx_ext="ws"` and `ws_connect=f"/agui/ws/{thread_id}"` — without these, the form's `ws_send` attribute has no WebSocket to send to (this was a real bug).

### utils/agent.py — LangGraph Agent

Uses `create_react_agent` from `langgraph.prebuilt` with XAI Grok via OpenAI-compatible API:
```python
ChatOpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1", model=MODEL_NAME)
```

6 tools as `StructuredTool`: 2 DB-backed (readiness_checkin, readiness_report), 4 conversational (return prompt frameworks for the LLM to present). Tools access the current user via `threading.local()` — `set_current_user()` is called in `_handle_ai_run()` before streaming starts.

Agent is created per-thread via `create_mentastic_agent(user_id)`, cached on the AGUIThread instance.

### Database Pattern

Synchronous SQLAlchemy with raw SQL via `text()`. No ORM models — all queries use `mentastic.` schema prefix. The `DatabasePool` class auto-commits on context exit, auto-rollbacks on exception. Singleton instances in auth.py and chat_store.py.

5 tables: `users`, `chat_conversations`, `chat_messages`, `readiness_checkins`, `session_summaries`.

### Auth

bcrypt + FastHTML session dict. No decorators — routes check `session.get("user")` directly. Auth forms loaded via HTMX into `#auth-forms` div. JWT helpers exist but aren't used for web sessions (future API use).

## Key Patterns

- **OOB Swaps**: All WebSocket updates use `hx_swap_oob` to update multiple DOM targets (chat messages, trace panel, input form, conversation list) from a single WS message.
- **Guard flag**: `window._aguiProcessing` JS flag prevents double-submit while streaming.
- **Markdown rendering**: Streamed tokens arrive as raw text. After streaming completes, the full response is rendered server-side with Python `markdown` library and sent as an OOB swap replacing the streaming span. Historical messages use FastHTML's `MarkdownJS()` with the `.marked` class for client-side rendering.
- **Thread lifecycle**: Threads are in-memory only. Messages persist in DB, but the AGUIThread object (with its agent and WS connections) is lost on app restart.
- **Static files**: FastHTML serves from `static/` directory at root URLs (`/sw.js`, not `/static/sw.js`). The `/manifest.json` route is explicit because FastHTML doesn't auto-serve `.json`.

## FastHTML Best Practices

Reference: `fashtml-ctx.txt` in the repo root.

- Use `serve()` instead of `if __name__ == "__main__"` + `uvicorn.run()` — `serve()` handles this internally
- Use `MarkdownJS()` and `HighlightJS()` in `hdrs` for client-side markdown/code rendering
- Use `NotStr()` to inject raw HTML into FastTags without escaping (e.g. `Div(NotStr(rendered_html))`)
- Prefer Python over JS. Never use React/Vue/Svelte — FastHTML is HTMX-first
- `cls` maps to `class`, `_for` maps to `for`, `hx_get` maps to `hx-get` (underscores → hyphens)
- Route functions can be used directly in attributes (`hx_get=my_route` instead of `hx_get="/path"`)
- FastHTML is NOT FastAPI — it's for HTML-first apps, not API services
- When returning responses: FTs/tuples auto-render to HTML; `Title` in a tuple auto-goes to `<head>`
- WebSocket pattern: `fast_app(exts='ws')` + `Div(hx_ext='ws', ws_connect='/ws')` + `Form(ws_send=True)`
- HTMX OOB swaps do NOT execute `<script>` tags — use server-side rendering instead of client-side JS for dynamic content updates

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `DB_URL` | yes | — |
| `XAI_API_KEY` | yes | — |
| `MODEL_NAME` | no | `grok-4-fast-reasoning` |
| `JWT_SECRET` | no | `mentastic-dev-secret` |
| `PORT` | no | `5010` |
| `RELOAD` | no | `true` |
