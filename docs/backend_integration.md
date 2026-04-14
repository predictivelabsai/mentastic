# Backend Integration — mentastic-ai

This document compares the current frontend capabilities (this repo: `mentastic`) with the full backend API (`mentastic-ai`), identifies what we gain from integration, and outlines the integration steps.

---

## Current Local Capabilities (mentastic frontend)

The frontend runs as a standalone FastHTML app with its own LangGraph agent. It works without the backend API.

| Capability | Implementation |
|---|---|
| LLM | XAI Grok via OpenAI-compatible API (`grok-4-fast-reasoning`) |
| Agent | `create_react_agent` (LangGraph prebuilt) — single-node ReAct |
| Tools | 6 tools: readiness_checkin, readiness_report, performance_scan, recovery_plan, stress_load_analysis, resilience_builder |
| Streaming | WebSocket via HTMX `ws-send` + `astream_events(v2)` |
| Auth | Clerk (email/Google/Apple) + fallback email/password |
| Database | PostgreSQL with 5 tables (users, chat_conversations, chat_messages, readiness_checkins, session_summaries) |
| Chat history | Persisted per-thread with conversation list |
| Markdown | Server-side rendering after streaming completes |
| Dashboard | Mock data with inline SVG charts |
| Integrations | Mock connection flow (in-memory state) |

**Limitations:**
- No conversation routing (every message goes through the same ReAct agent)
- No meaningful message classifier (bootstrap responses wasteful on greetings)
- No sentinel/safety system
- No passive data from wearables (Thryve integration is UI-only)
- No questionnaire system (WHO-5, onboarding)
- No session summaries or meta-summaries
- No report generation or fetching
- No MLflow experiment tracking
- Single LLM provider (XAI only)
- No conversation evaluation
- Tools return text frameworks, not actual data analysis

---

## What We Gain from Backend Integration

The `mentastic-ai` backend is a FastAPI service with a sophisticated multi-agent LangGraph conversation system, 30+ database tables, and deep health data integration.

### 1. Multi-Agent Conversation Graph

**Current:** Single ReAct agent handles everything.
**Backend:** 6-node StateGraph with conditional routing:

```
router → bootstrap_agent (lightweight greetings)
       → intent_agent → reports_agent → conversation_agent
       → conversation_agent → tool_executor → (loop or END)
```

- **Router agent** — Deterministic routing based on message significance, sentinel instructions, and user intent
- **Bootstrap agent** — Returns a single-sentence opening for non-meaningful messages (saves LLM tokens)
- **Intent agent** — Handles explicit intents: CHECK_IN, LATEST_REPORT, QUESTIONNAIRE_COMPLETED
- **Reports agent** — Fetches and prepares reports from the ai-aux service
- **Conversation agent** — Full LLM conversation with 7+ tools, system prompt injection, plan artefact context
- **Tool executor** — Executes tools with special widget handling (mood check-in, report display, questionnaire launch)

### 2. Meaningful Message Classifier

**Current:** Every message triggers a full LLM call.
**Backend:** LLM-based classifier (gpt-4o-mini) determines if a message is meaningful before routing. Greetings like "hi" or "thanks" get a fast bootstrap response. Saves ~70% of LLM calls on non-substantive messages.

### 3. Sentinel Safety System

**Current:** No safety checks.
**Backend:** Sentinel agent provides:
- Session-level safety classification (`is_safe` flag)
- Proactive questionnaire suggestions (e.g., "Your patterns suggest a WHO-5 assessment would be helpful")
- Proposed action widgets (e.g., suggest mood check-in after detecting stress patterns)
- Safety fallback messages when sessions are flagged

### 4. Passive Data Integration (Thryve)

**Current:** Mock integration cards, no real data.
**Backend:** Full Thryve passive data tools:
- `fetch_passive_data()` — Access 300+ data types: steps (1000), sleep (2000), heart rate (3000), stress (6010), mood (5115), HRV, SpO2, body temperature, etc.
- `fetch_user_data_overview()` — Categorised health data summary
- Daily data (90-day lookback) and intraday data (7-day lookback)
- Patrick can reference real wearable data in conversations: "Your Oura ring shows your HRV dropped 15% this week — that correlates with the stress you mentioned."

### 5. Questionnaire System

**Current:** Not implemented.
**Backend:** Full psychometric assessment system:
- **WHO-5** — 5-question mental well-being assessment (0-25 score, max 100%)
- **Onboarding questionnaire** — Initial assessment during signup, determines user suitability
- Multi-language support (questions served in user's language)
- LLM-guided flow — Patrick administers questions conversationally
- Score calculation, dimension tracking, completion timestamps
- Questionnaire results feed back into Patrick's conversation context

### 6. Report System

**Current:** readiness_report tool queries local check-ins only.
**Backend:** Full report generation and display:
- Morning and evening reports generated from passive + active data
- `fetch_reports()` tool — Date range and type filtering
- `show_report_widget()` — Triggers native report display in app
- Reports include AI-generated insights, trends, and recommendations
- Report data stored with content, images, read/liked tracking

### 7. Session Intelligence

**Current:** Messages saved but no summarisation.
**Backend:** Multi-level conversation memory:
- **Session summaries** — Automatic summarisation at session end (tone, energy, engagement, topics)
- **Meta-summary** — Long-term user profile (behavioural patterns, themes, goals, follow-through)
- **User updates registry** — Event-driven updates shown in bootstrap messages ("Since last time: your WHO-5 score improved")
- **Plan artefacts** — Hierarchical goals injected into conversation context

### 8. Multi-LLM Support

**Current:** XAI Grok only.
**Backend:** LLM factory supporting 4 providers:
- OpenAI (gpt-5.2, gpt-4o-mini)
- Anthropic (Claude)
- Google (Gemini)
- Mistral

Configurable per-request via `llm_provider` and `llm_model` parameters.

### 9. MLflow Experiment Tracking

**Current:** No tracking.
**Backend:** Full MLflow integration:
- Conversation traces with span types
- WHO-5 and onboarding logs
- Automated evaluation via ai-aux service
- Azure blob storage for artefacts
- Environment-specific experiments (dev/test/prod)

### 10. Advanced Tools

**Current:** 6 tools (2 DB-backed, 4 conversational).
**Backend:** 9+ tools:
- `fetch_reports()` — Historical report data
- `fetch_passive_data()` — 300+ Thryve data types
- `fetch_user_data_overview()` — Health summary
- `show_mood_check_in_widget()` — Trigger mood widget
- `show_report_widget()` — Display report
- `show_mood_check_in_graph_widget()` — Mood trends graph
- `resolve_questionnaire_request()` — LLM-powered questionnaire selection
- `fetch_questionnaire_results()` — Historical questionnaire scores
- `web_search()` — DuckDuckGo search

---

## Local API Simulator

Before integrating with the real backend, use the local API simulator to develop and test the frontend integration layer. The simulator lives in `api/` and mirrors all backend endpoints with mock responses and in-memory state.

### Setup

```bash
# Install dependencies (fastapi, uvicorn already in requirements.txt)
pip install -r requirements.txt

# Start the simulator
.venv/bin/python -m api.simulator
# Runs on http://localhost:8181 (same port as real backend)
# Swagger docs: http://localhost:8181/docs
```

### Configure the frontend

Add to `.env`:
```
BACKEND_API_URL=http://localhost:8181
```

The frontend should check this variable. When set, `AGUIThread._handle_ai_run()` calls the simulator instead of the local LangGraph agent. When unset, the local agent is used as a fallback.

### What the simulator provides

| Endpoint | Simulator Behavior |
|----------|-------------------|
| `GET /health` | Always returns `{"status": "healthy"}` |
| `POST /v0/conversation` | Topic-aware mock replies (detects greetings, sleep, stress, goals, check-ins, reports) |
| `POST /v0/conversation/stream` | SSE stream — word-by-word TOKEN events (~30ms/token) + DONE event with full message |
| `POST /v0/conversation/widget-interaction` | Logs to in-memory list, returns 202 |
| `POST /v0/questionnaires/who5` | Stateful 5-question WHO-5 flow with real answer choices |
| `GET /v0/questionnaires/who5_results` | Returns mock dimension scores |
| `POST /v0/questionnaires/who5_results` | Saves to in-memory dict |
| `POST /v0/questionnaires/onboarding` | Stateful 3-question onboarding flow |

### Schemas

`api/schemas.py` contains Pydantic models that exactly match the backend contracts (`ChatRequest`, `ChatResponse`, `StreamingEvent`, `Who5Request`, etc.). When switching from simulator to real backend, only the URL changes — request/response shapes are identical.

### Testing the simulator

```bash
# Health check
curl http://localhost:8181/health

# Non-streaming chat
curl -X POST http://localhost:8181/v0/conversation \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","user_input":"How is my sleep?"}'

# Streaming chat (watch SSE events)
curl -N -X POST http://localhost:8181/v0/conversation/stream \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","user_input":"hello"}'

# WHO-5 start
curl -X POST http://localhost:8181/v0/questionnaires/who5 \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","user_input":"hello","session_id":"s1"}'
```

### Simulator vs real backend

| Aspect | Simulator | Real Backend |
|--------|-----------|--------------|
| Auth | None (no JWT required) | JWT via Clerk JWKS |
| LLM | Mock responses (no API calls) | OpenAI/Anthropic/Google/Mistral |
| Database | In-memory dicts (lost on restart) | PostgreSQL (30+ tables) |
| Streaming | Word-by-word split of pre-built reply | Real LLM token streaming |
| Agent | No agent — pattern matching | 6-node LangGraph StateGraph |
| Port | 8181 | 8181 |

For full API reference, see [local_api_docs.md](local_api_docs.md).

---

## Integration Steps

### Phase 1: Connect Frontend to Backend API (SSE streaming)

Replace the local LangGraph agent with calls to the backend `/v0/conversation/stream` endpoint.

**Changes in `mentastic` (frontend):**

1. **Add `BACKEND_API_URL` to `.env`:**
   ```
   BACKEND_API_URL=http://localhost:8181
   ```

2. **Modify `AGUIThread._handle_ai_run()`** in `app.py`:
   - Instead of calling `agent.astream_events()` locally, make an HTTP POST to `{BACKEND_API_URL}/v0/conversation/stream`
   - Parse SSE events (`TOKEN`, `DONE`, `ERROR`) and translate to the existing OOB swap pattern
   - Forward `user_id`, `session_id`, `user_input` from the session

3. **Map backend events to frontend OOB swaps:**
   ```python
   # Backend SSE event → Frontend WebSocket OOB swap
   TOKEN → Span(delta, id=content_id, hx_swap_oob="beforeend")
   DONE  → Server-rendered markdown swap + re-enable input
   ERROR → Error message display
   ```

4. **Handle action widgets:**
   - `DONE` events may include `action_widget` and `action_widget_details`
   - Map to frontend UI: mood check-in form, report display, questionnaire launcher

5. **Keep local agent as fallback:**
   - If `BACKEND_API_URL` is not set, continue using the local ReAct agent
   - This preserves the standalone demo capability

### Phase 2: Integrate Questionnaires

1. **Add questionnaire routes** to `app.py`:
   - `POST /questionnaire/who5` — Proxy to backend `/v0/questionnaires/who5`
   - Render WHO-5 questions in the chat interface
   - Display score and summary after completion

2. **Add onboarding flow:**
   - After Clerk registration, trigger onboarding questionnaire
   - `POST /questionnaire/onboarding` — Proxy to backend
   - Results determine initial Patrick context

### Phase 3: Connect Real Passive Data

1. **Wire Thryve integration:**
   - When user connects a wearable on `/integrations`, call backend to register the data source
   - Backend's `fetch_passive_data()` tool becomes available to Patrick
   - Dashboard pulls real data instead of mock data

2. **Replace mock dashboard** with backend data:
   - `GET /v0/reports` for report history
   - Passive data overview for chart data
   - Real readiness scores from check-ins + wearable data

### Phase 4: Session Intelligence

1. **Enable session summaries:**
   - Backend automatically summarises sessions
   - Frontend fetches and injects into conversation context

2. **Enable meta-summary:**
   - Long-term user profile updates
   - Patrick references prior sessions: "Last week you mentioned..."

3. **Enable user updates:**
   - Bootstrap messages include relevant updates
   - "Since we last spoke, your WHO-5 score improved by 8%"

### Phase 5: Safety & Sentinel

1. **Forward sentinel instructions** to frontend:
   - If backend suggests a questionnaire, show it in the chat
   - If session flagged as unsafe, display safety resources

2. **Implement `is_safe` handling:**
   - Check `DONE` event `is_safe` field
   - If false, show crisis resources and contact information

---

## Architecture After Integration

```
Browser (FastHTML + HTMX)
    ↓ WebSocket
AGUIThread (app.py)
    ↓ HTTP POST /v0/conversation/stream (SSE)
mentastic-ai (FastAPI)
    ↓ LangGraph StateGraph
    ├── RouterAgent
    ├── BootstrapAgent  
    ├── IntentAgent
    ├── ConversationAgent (7+ tools)
    │   ├── fetch_passive_data (Thryve)
    │   ├── fetch_reports
    │   ├── widget tools
    │   ├── questionnaire tools
    │   └── web_search
    ├── ReportsAgent
    └── ToolExecutor
    ↓
    ├── PostgreSQL (30+ tables)
    ├── Thryve Health API (500+ wearables)
    ├── ai-aux service (reports, evaluation)
    └── MLflow (experiment tracking)
```

---

## Environment Variables After Integration

| Variable | Service | Description |
|---|---|---|
| `DB_URL` | frontend | Frontend PostgreSQL (users, chat) |
| `XAI_API_KEY` | frontend | Local agent fallback |
| `BACKEND_API_URL` | frontend | mentastic-ai API URL |
| `DATABASE_URL` | backend | Backend PostgreSQL (30+ tables) |
| `OPEN_AI_API_KEY` | backend | Primary LLM |
| `ANTHROPIC_API_KEY` | backend | Optional: Claude |
| `AI_AUX_URL` | backend | Reports, evaluation service |
| `MLFLOW_TRACKING_URI` | backend | Experiment tracking |
| `CLERK_PUBLISHABLE_KEY` | frontend | Auth UI |
| `CLERK_SECRET_KEY` | frontend | JWT verification |

---

## Summary

| Capability | Local Only | With Backend |
|---|---|---|
| Agent architecture | Single ReAct | 6-node multi-agent graph |
| Message routing | None | Router + bootstrap + intent |
| Safety | None | Sentinel + is_safe flag |
| Wearable data | Mock | 300+ Thryve data types |
| Questionnaires | None | WHO-5 + onboarding + custom |
| Reports | Basic check-in trends | Morning/evening AI reports |
| Session memory | Message history only | Summaries + meta-summary + updates |
| LLM providers | XAI only | OpenAI + Anthropic + Google + Mistral |
| Experiment tracking | None | MLflow with evaluation |
| Tools | 6 | 9+ with real data access |
| Database tables | 5 | 30+ |
