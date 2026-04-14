# Local API Simulator — Reference

The local API simulator (`api/simulator.py`) is a FastAPI mock of the `mentastic-ai` backend. It mirrors all 8 backend endpoints with in-memory state and mock responses, enabling frontend development and testing without running the real backend or any external services.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the simulator (port 8181)
.venv/bin/python -m api.simulator

# Swagger UI
open http://localhost:8181/docs
```

Set `BACKEND_API_URL=http://localhost:8181` in `.env` to point the frontend at the simulator.

---

## Folder Structure

```
api/
├── __init__.py
├── schemas.py      # Pydantic models — exact match of backend contracts
└── simulator.py    # FastAPI app with all 8 endpoints + mock logic
```

- **`schemas.py`** — Pydantic request/response models copied from the `mentastic-ai` backend (`ChatRequest`, `ChatResponse`, `StreamingEvent`, `Who5Request`, `Who5Response`, `OnboardingRequest`, `OnboardingResponse`, etc.). These are the API contracts — identical to the real backend.
- **`simulator.py`** — FastAPI application with all endpoint handlers, mock response logic, in-memory session state, and SSE streaming support.

---

## Endpoints

### Health Check

```
GET /health
```

Returns service status. No authentication required.

**Response:**
```json
{
  "status": "healthy",
  "message": "Simulator is running (no database)"
}
```

---

### Conversation — Non-Streaming

```
POST /v0/conversation
```

Processes a user message and returns a complete response.

**Request body (`ChatRequest`):**
```json
{
  "user_id": "user-123",
  "session_id": "optional-session-id",
  "user_input": "How is my sleep?",
  "user_data": {},
  "system_prompt_from_admin": false,
  "intent": null,
  "starter_prompt": false,
  "llm_provider": "openai",
  "llm_model": "gpt-5.2"
}
```

Required fields: `user_id`, `user_input`. All others have defaults.

**Response body (`ChatResponse`):**
```json
{
  "assistant_message": "Based on your recent patterns, your sleep...",
  "session_id": "generated-uuid-if-not-provided",
  "is_safe": true,
  "questionnaire_id": null,
  "action_widget": null,
  "action_widget_details": null
}
```

**Mock behavior:** The simulator detects topic keywords in the user input and returns contextually relevant responses:

| Input contains | Response topic |
|----------------|---------------|
| "hi", "hello", "hey", etc. | Random greeting |
| "check-in", "checkin" | Readiness check-in prompt (4 dimensions) |
| "report" | Mock readiness summary with scores |
| "sleep" | Sleep analysis with improvement tips |
| "stress", "anxious" | Stress management techniques |
| "goal", "plan" | Goal-setting framework |
| (anything else) | Generic conversational response |

---

### Conversation — Streaming (SSE)

```
POST /v0/conversation/stream
```

Same request body as `/v0/conversation`. Returns a Server-Sent Events stream.

**SSE event format:**

Each event has a type (`TOKEN`, `DONE`, or `ERROR`) and a JSON data payload.

```
event: TOKEN
data: {"delta": "Based", ...}

event: TOKEN
data: {"delta": " on", ...}

...

event: DONE
data: {"assistant_message": "Based on your recent...", "session_id": "...", "is_safe": true}
```

**`TOKEN` event data (`StreamingEventData`):**
```json
{
  "delta": " word",
  "assistant_message": null,
  "questionnaire_id": null,
  "action_widget": null,
  "action_widget_details": null,
  "session_id": null,
  "is_safe": null,
  "error": null
}
```

**`DONE` event data:**
```json
{
  "delta": null,
  "assistant_message": "Full response text here...",
  "questionnaire_id": null,
  "action_widget": null,
  "action_widget_details": null,
  "session_id": "session-uuid",
  "is_safe": true,
  "error": null
}
```

**`ERROR` event data:**
```json
{
  "delta": null,
  "assistant_message": null,
  "session_id": null,
  "is_safe": null,
  "error": "Error description"
}
```

**Streaming behavior:** Tokens are emitted word-by-word with ~30ms delay between each. The `DONE` event fires after all tokens.

**Testing with curl:**
```bash
curl -N -X POST http://localhost:8181/v0/conversation/stream \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","user_input":"Tell me about my stress levels"}'
```

---

### Conversation — Widget Interaction

```
POST /v0/conversation/widget-interaction
```

Saves the result of a UI widget interaction (mood check-in, report display, etc.).

**Request body (`WidgetInteractionRequest`):**
```json
{
  "user_id": "user-123",
  "session_id": "session-456",
  "action_widget": "MCI",
  "action_widget_details": {"mood": 7, "timestamp": "2026-04-14T10:00:00Z"}
}
```

**`action_widget` values (`ActionWidgets` enum):**

| Value | Meaning |
|-------|---------|
| `MCI` | Mood check-in |
| `SUMMARY` | Session summary |
| `MCI_GRAPH` | Mood check-in graph |
| `QUESTIONNAIRE` | Questionnaire launch |

**Response:** Empty body, HTTP 202 Accepted.

---

### WHO-5 Questionnaire

```
POST /v0/questionnaires/who5
```

Stateful questionnaire flow. Send "hello" or a greeting to start, then send answers to advance through 5 questions.

**Request body (`Who5Request`):**
```json
{
  "user_id": "user-123",
  "session_id": "who5-session-1",
  "user_input": "hello",
  "user_data": {},
  "system_prompt_from_admin": false,
  "llm_provider": "openai",
  "llm_model": "gpt-4o"
}
```

**Response body (`Who5Response`):**
```json
{
  "assistant_message": "Welcome to the WHO-5... **Question 1/5:** ...",
  "is_survey_complete": false,
  "session_id": "who5-session-1",
  "answers": [
    "All of the time",
    "Most of the time",
    "More than half of the time",
    "Less than half of the time",
    "Some of the time",
    "At no time"
  ],
  "answer_type": "SINGLE",
  "final_score": null,
  "is_safe": true
}
```

**Flow:**
1. Send greeting → returns question 1 with answer choices
2. Send answer text → returns question 2
3. Repeat for questions 3-5
4. After question 5, returns `is_survey_complete: true` with `final_score: 68.0`

State is tracked per `session_id`. Reusing a session_id continues where you left off.

---

### WHO-5 Results — Get

```
GET /v0/questionnaires/who5_results?user_id=user-123
```

Returns WHO-5 scores and dimension breakdown for a user.

**Response body (`Who5SummaryResponse`):**
```json
{
  "user_id": "user-123",
  "summary": "Overall moderate well-being with stable patterns over the past month.",
  "final_score": 68.0,
  "dimensions": [
    {"name": "Cheerful and in good spirits", "score": 4, "max_score": 5},
    {"name": "Calm and relaxed", "score": 3, "max_score": 5},
    {"name": "Active and vigorous", "score": 3, "max_score": 5},
    {"name": "Fresh and rested", "score": 3, "max_score": 5},
    {"name": "Interesting daily life", "score": 4, "max_score": 5}
  ]
}
```

Returns mock data for any `user_id`. If a summary was previously saved via POST, returns that instead.

---

### WHO-5 Results — Save

```
POST /v0/questionnaires/who5_results
```

Saves a WHO-5 summary for a user.

**Request body (`Who5SummaryRequest`):**
```json
{
  "user_id": "user-123",
  "final_score": 72.0,
  "completed_at": "2026-04-14T10:00:00Z",
  "dimensions": [4, 3, 4, 3, 4]
}
```

**Response:**
```json
{"message": "WHO-5 summary saved successfully"}
```

Saved data is returned by subsequent `GET /v0/questionnaires/who5_results` calls for the same `user_id`.

---

### Onboarding Questionnaire

```
POST /v0/questionnaires/onboarding
```

Stateful 3-question onboarding flow to determine user profile and suitability.

**Request body (`OnboardingRequest`):**
```json
{
  "user_id": "user-123",
  "session_id": "onboard-1",
  "user_input": "hello",
  "user_data": {},
  "llm_provider": "openai",
  "llm_model": "gpt-4o"
}
```

**Response body (`OnboardingResponse`):**
```json
{
  "assistant_message": "Welcome! Let's get to know you a bit. What best describes your primary goal?",
  "answers": ["Improve sleep", "Manage stress", "Boost performance", "Track wellness", "Other"],
  "answer_type": "MULTIPLE",
  "question_number": 1,
  "is_survey_complete": false,
  "is_user_suitable": true,
  "session_id": "onboard-1"
}
```

**Flow:**
1. Send greeting → question 1 (primary goal, 5 choices)
2. Send answer → question 2 (fitness level, 4 choices)
3. Send answer → question 3 (wearable usage, 4 choices)
4. Send answer → `is_survey_complete: true`, `is_user_suitable: true`

State is tracked per `user_id`.

---

## Simulator vs Real Backend

| Aspect | Simulator (`api/simulator.py`) | Real Backend (`mentastic-ai`) |
|--------|-------------------------------|-------------------------------|
| Auth | None (no JWT required) | JWT via Clerk JWKS verification |
| LLM | Mock responses (no API calls) | OpenAI / Anthropic / Google / Mistral |
| Database | In-memory dicts (lost on restart) | PostgreSQL (30+ tables, async) |
| Streaming | Word-by-word split of pre-built reply | Real LLM token streaming |
| Agent | Keyword-based pattern matching | 6-node LangGraph StateGraph |
| Safety | Always `is_safe: true` | Sentinel agent with safety classification |
| Questionnaires | Fixed question set, mock scores | LLM-guided flow with real scoring |
| Port | 8181 | 8181 |
| Schemas | Identical Pydantic models | Source of truth |

To switch from simulator to real backend, change `BACKEND_API_URL` in `.env` to point at the real backend and add a JWT `Authorization` header to requests.

---

## Using with httpx (Python)

```python
import httpx

BASE = "http://localhost:8181"

# Non-streaming
resp = httpx.post(f"{BASE}/v0/conversation", json={
    "user_id": "test",
    "user_input": "How am I doing?"
})
print(resp.json()["assistant_message"])

# Streaming
with httpx.stream("POST", f"{BASE}/v0/conversation/stream", json={
    "user_id": "test",
    "user_input": "Tell me about stress management"
}) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:"):
            print(line)
```

---

## Extending the Simulator

To add new mock endpoints:

1. Add Pydantic models to `api/schemas.py` matching the backend contract
2. Add a route handler in `api/simulator.py`
3. Use in-memory dicts for state (prefix with `_`)

The simulator intentionally has no external dependencies beyond FastAPI — no database, no LLM keys, no auth provider.
