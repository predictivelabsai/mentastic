# Mentastic Architecture

Mentastic is built as a single-process server-rendered application using the **AG UI** (Agentic Graphical User Interface) pattern — a design philosophy where the AI agent is not hidden behind an API, but is the interface itself. The user interacts directly with the agent through a streaming conversational UI, while the system makes its reasoning process visible in real time.

This document describes the system architecture, the AG UI concept, the 3-pane design, and the technical flow from user input to agent response.

---

## The AG UI Concept

Traditional AI applications treat the model as a backend service: the user fills a form, the server calls an API, and a result is returned. AG UI inverts this. The agent becomes a first-class participant in the interface — it streams its thinking, shows tool calls as they happen, and the user watches the reasoning unfold token by token.

In Mentastic, this means:

- **Streaming-first interaction.** Every response from Patrick (the AI companion) is streamed via WebSocket. The user sees tokens appear in real time, not after a loading spinner.
- **Transparent tool execution.** When Patrick calls a tool (e.g. saving a readiness check-in to the database, or generating a resilience exercise plan), the tool call appears in the Thinking Trace panel — the user can see what the agent decided to do and why.
- **Conversational agency.** The 6 welcome cards are not static forms — they are conversation starters. Clicking "Readiness Check-In" sends a natural language message to Patrick, who then uses the appropriate tool, asks follow-up questions, and provides personalised insight. The agent decides the flow, not a hardcoded wizard.
- **No page reloads.** The entire interaction happens over a single WebSocket connection using HTMX out-of-band (OOB) swaps. The chat, trace panel, conversation list, and input state all update simultaneously from a single message stream.

This is fundamentally different from a chatbot with a text box. AG UI makes the agent's reasoning visible and the interaction feel collaborative rather than transactional.

---

## 3-Pane Design Principles

The interface is organised into three panes, each serving a distinct purpose in the agent interaction:

**Left Pane (260px) — Context & Navigation.** This is the user's anchor. It shows who they are (auth state), what conversations they've had (history), and what Mentastic is (About section). It provides orientation without competing with the active conversation.

**Center Pane (flexible) — Conversation.** This is where the work happens. The chat area shows the streaming dialogue with Patrick, including user messages, assistant responses with rendered markdown, and tool execution indicators. The welcome screen with 6 action cards appears for new conversations, providing guided entry points into Patrick's capabilities.

**Right Pane (380px, toggled) — Thinking Trace.** This is what makes AG UI different from a standard chatbot. The trace panel shows the agent's internal activity: when a tool is called, what it's doing, and when it completes. This transparency builds trust — the user understands why Patrick recommended a specific recovery plan or how it analysed their stress patterns. The trace panel opens automatically during AI runs and can be toggled on demand.

On mobile (< 768px), the layout collapses to a single center pane, keeping the conversation front and center.

```mermaid
graph TB
    subgraph "App Layout (CSS Grid)"
        direction LR
        subgraph "Left Pane (260px)"
            BRAND[Mentastic + PATRICK badge]
            NEWCHAT[+ New Chat]
            CONVLIST[Conversation History]
            ABOUT[About Mentastic]
            AUTH[Login / Register<br/>or User Info + Logout]
        end

        subgraph "Center Pane (1fr)"
            HEADER[Patrick + Trace button]
            subgraph "Chat Container (hx-ext=ws)"
                WELCOME[Welcome Screen<br/>6 Action Cards]
                MESSAGES[Chat Messages<br/>User + Assistant bubbles]
                INPUT[Input Form<br/>ws-send]
            end
        end

        subgraph "Right Pane (380px, toggled)"
            TRACE[Thinking Trace<br/>Tool calls + status]
        end
    end

    WELCOME -->|Card click| INPUT
    INPUT -->|WebSocket| MESSAGES
    MESSAGES -.->|OOB swap| TRACE
```

---

## System Overview

The system is a single Python process running FastHTML (a Starlette-based framework for server-rendered HTMX applications). There is no separate frontend build, no API gateway, and no message queue. The browser connects via HTTP for the initial page load and then upgrades to a WebSocket for the chat session.

The LangGraph agent runs in-process, streaming events directly to the WebSocket handler. PostgreSQL stores user accounts, conversation history, and readiness check-in data. The LLM (XAI Grok) is accessed via an OpenAI-compatible API.

```mermaid
graph TB
    subgraph Browser
        UI[3-Pane FastHTML UI]
        WS[WebSocket Connection]
        HTMX[HTMX + marked.js]
    end

    subgraph "FastHTML Server (port 5010)"
        APP[app.py]
        AGUI[AGUISetup]
        THREAD[AGUIThread]
        UIC[UI Renderer]
    end

    subgraph "LangGraph Agent"
        AGENT[ReAct Agent]
        LLM[XAI Grok LLM]
        TOOLS[6 Tools]
    end

    subgraph "PostgreSQL (mentastic schema)"
        USERS[(users)]
        CONV[(chat_conversations)]
        MSGS[(chat_messages)]
        CHECKINS[(readiness_checkins)]
        SUMMARIES[(session_summaries)]
    end

    UI -->|HTTP GET /| APP
    UI -->|WS /agui/ws/thread_id| WS
    WS --> AGUI
    AGUI --> THREAD
    THREAD --> UIC
    THREAD -->|astream_events v2| AGENT
    AGENT --> LLM
    AGENT --> TOOLS
    TOOLS -->|DB-backed tools| CHECKINS
    THREAD -->|save messages| MSGS
    THREAD -->|save conversations| CONV
    APP -->|auth| USERS
    LLM -->|streaming tokens| THREAD
    THREAD -->|OOB swap HTML| WS
```

---

## WebSocket Streaming Flow

When a user sends a message, the following sequence occurs — all within a single WebSocket connection, with no page reloads or HTTP round-trips:

1. The user's message is immediately rendered as a chat bubble (optimistic UI).
2. An empty assistant bubble is created with a streaming cursor.
3. The LangGraph agent begins processing, and its events are streamed back.
4. Each token from the LLM is appended to the assistant bubble in real time via HTMX OOB swap.
5. If the agent calls a tool, the tool execution appears in both the chat (as a status indicator) and the Thinking Trace panel.
6. When streaming completes, the raw text is replaced with server-side rendered markdown (bold, lists, headings), the input is re-enabled, and the conversation list is refreshed.

The entire flow takes approximately 0.5 seconds to first token and 2-3 seconds for a complete response.

```mermaid
sequenceDiagram
    participant B as Browser
    participant WS as WebSocket
    participant T as AGUIThread
    participant A as LangGraph Agent
    participant L as XAI Grok LLM
    participant DB as PostgreSQL

    B->>WS: Connect /agui/ws/{thread_id}
    B->>WS: Send message (ws-send)
    WS->>T: _handle_message(msg)
    T->>T: Set guard flag (prevent double-submit)
    T->>B: User bubble (OOB beforeend)
    T->>B: Empty assistant bubble (OOB beforeend)
    T->>B: Trace: "Patrick is thinking..." (OOB beforeend)
    T->>DB: save_message(user msg)

    T->>A: astream_events(messages, v2)

    loop Token Streaming
        A->>L: Chat completion (streaming)
        L-->>A: Token chunk
        A-->>T: on_chat_model_stream event
        T->>B: Span token (OOB beforeend to content_id)
    end

    opt Tool Call
        A-->>T: on_tool_start event
        T->>B: Tool indicator in chat (OOB)
        T->>B: Tool trace entry (OOB)
        A->>A: Execute tool
        A-->>T: on_tool_end event
        T->>B: Update tool status (OOB outerHTML)
    end

    T->>B: Server-rendered markdown (OOB outerHTML)
    T->>B: Trace: "Response complete"
    T->>DB: save_message(assistant response)
    T->>B: Re-enable input, refresh conversation list
```

---

## Agent Architecture

Patrick is built using LangGraph's `create_react_agent` — a ReAct (Reasoning + Acting) agent that can decide when to call tools and when to respond directly. The agent has access to 6 tools, split into two categories:

**DB-backed tools** persist data and query historical patterns. When a user does a readiness check-in, the values are saved to PostgreSQL and available for future trend analysis. The readiness report tool aggregates check-ins over configurable time windows and detects upward stress trends or declining energy.

**Conversational tools** return structured frameworks that Patrick uses to guide the conversation. These don't touch the database — they provide evidence-based content (recovery techniques, resilience exercises, stress assessment frameworks) that Patrick weaves into a personalised dialogue. This means the same tool can produce very different conversations depending on the user's context.

The LLM model is configurable via the `MODEL_NAME` environment variable, defaulting to `grok-4-fast-reasoning`. The agent is created per-conversation thread and cached, so each thread maintains its own tool state and user context.

```mermaid
graph LR
    subgraph "Patrick — ReAct Agent"
        direction TB
        SP[System Prompt<br/>Performance & Readiness]
        LLM[XAI Grok<br/>MODEL_NAME env var]
    end

    subgraph "DB-Backed Tools"
        T1[readiness_checkin<br/>energy/focus/stress/mood 1-10]
        T2[readiness_report<br/>7d/14d/30d trends]
    end

    subgraph "Conversational Tools"
        T3[performance_scan<br/>6-area guided interview]
        T4[recovery_plan<br/>physical/cognitive/emotional]
        T5[stress_load_analysis<br/>demand vs resource audit]
        T6[resilience_builder<br/>6 focus areas]
    end

    SP --> LLM
    LLM --> T1
    LLM --> T2
    LLM --> T3
    LLM --> T4
    LLM --> T5
    LLM --> T6

    T1 -->|INSERT| DB[(mentastic.readiness_checkins)]
    T2 -->|SELECT| DB

    subgraph "User Context"
        TL[threading.local<br/>set_current_user]
    end

    TL -.->|user_id| T1
    TL -.->|user_id| T2
```

---

## Database Schema

The database uses a dedicated `mentastic` schema with 5 tables. The design prioritises simplicity — no ORM models, just raw SQL via SQLAlchemy's `text()` function with named parameters. This makes the data layer easy to understand and debug.

The `readiness_checkins` table is the core data model for the DB-backed tools. Each check-in captures a snapshot of the user's state across four dimensions (energy, focus, stress, mood) on a 1-10 scale, with optional free-text notes. The readiness report tool queries this table to identify trends and generate personalised insights.

```mermaid
erDiagram
    users {
        serial id PK
        uuid user_id UK
        varchar email UK
        varchar password_hash
        varchar display_name
        boolean is_admin
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    chat_conversations {
        uuid thread_id PK
        uuid user_id FK
        varchar title
        timestamptz created_at
        timestamptz updated_at
    }

    chat_messages {
        bigserial id PK
        uuid thread_id FK
        uuid message_id
        varchar role
        text content
        jsonb metadata
        timestamptz created_at
    }

    readiness_checkins {
        serial id PK
        uuid user_id FK
        integer energy
        integer focus
        integer stress
        integer mood
        text notes
        timestamptz created_at
    }

    session_summaries {
        serial id PK
        uuid user_id FK
        uuid thread_id
        text summary
        timestamptz created_at
    }

    users ||--o{ chat_conversations : "owns"
    users ||--o{ readiness_checkins : "records"
    users ||--o{ session_summaries : "has"
    chat_conversations ||--o{ chat_messages : "contains"
```

---

## Class Hierarchy

The application code in `app.py` is structured around three classes that form the AG UI engine:

**AGUISetup** is the entry point. It wires WebSocket routes into the FastHTML app and maintains an in-memory registry of conversation threads. When a WebSocket connects, AGUISetup creates or retrieves the appropriate AGUIThread.

**AGUIThread** is the heart of the system. Each thread represents one conversation with one user. It holds the message history, manages WebSocket subscribers (supporting multiple browser tabs on the same conversation), and orchestrates the LangGraph agent. The `_handle_ai_run()` method is where streaming happens — it calls `agent.astream_events()` and translates each event into an OOB swap sent to all connected browsers.

**UI** is a stateless renderer. It produces the FastHTML components (welcome screen, message bubbles, input form) that AGUIThread sends to the browser. Separating rendering from state management keeps the code clean and testable.

```mermaid
classDiagram
    class AGUISetup {
        -app: FastHTML
        -_threads: Dict~str, AGUIThread~
        +chat(thread_id) Div
        +thread(thread_id, session) AGUIThread
        -_setup_routes()
        -_on_conn(ws, send, session)
        -_on_disconn(ws, session)
    }

    class AGUIThread {
        +thread_id: str
        -_user_id: str
        -_messages: list
        -_connections: Dict
        -_agent_instance: CompiledGraph
        +ui: UI
        +subscribe(conn_id, send)
        +unsubscribe(conn_id)
        +send(element)
        -_get_agent() CompiledGraph
        -_handle_message(msg, session)
        -_handle_ai_run(msg, session)
    }

    class UI {
        +thread_id: str
        +chat() Div
        -_render_message(msg) Div
        -_render_messages(msgs) Div
        -_render_input_form() Div
        -_render_welcome() Div
    }

    AGUISetup "1" --> "*" AGUIThread : manages
    AGUIThread "1" --> "1" UI : renders with
```

---

## Deployment

Mentastic is deployed as a single Docker container on Coolify at `mentastic.predictivelabs.ai`. The container runs `app.py` directly using FastHTML's built-in `serve()` function (which wraps Uvicorn). PostgreSQL and the XAI API are external services accessed via environment variables.

The architecture is intentionally simple — one process, one container, no orchestration. This makes it easy to deploy, debug, and iterate. The WebSocket connection requires that the reverse proxy (Coolify/Caddy) supports WebSocket upgrades, which is configured automatically.

```mermaid
graph LR
    subgraph "Coolify (mentastic.predictivelabs.ai)"
        DOCKER[Docker Container<br/>python:3.13-slim]
        APP[app.py :5010]
    end

    subgraph "External"
        PG[(PostgreSQL<br/>mentastic schema)]
        XAI[XAI API<br/>api.x.ai/v1]
    end

    DOCKER --> APP
    APP -->|DB_URL| PG
    APP -->|XAI_API_KEY| XAI
    
    USER[Browser] -->|HTTPS| DOCKER
    USER -->|WSS| DOCKER
```

---

## Resilience Builder: Tool Detail

The resilience builder is the most content-rich conversational tool. It contains 30 evidence-based exercises organised across 6 focus areas. When invoked, Patrick selects the appropriate set based on the user's request, presents them conversationally, and helps the user pick 1-2 to try that week.

This illustrates the AG UI philosophy: the tool provides the knowledge, but the agent provides the interaction. The same exercise set will be presented differently to a stressed executive versus a fatigued military operator, because Patrick adapts tone, emphasis, and follow-up questions to the individual.

```mermaid
mindmap
  root((Resilience Builder))
    General
      Box Breathing 4-4-4-4
      Micro-Recovery Breaks
      Evening Reflection
      Stress Inoculation
      Connection Practice
    Stress
      Progressive Muscle Relaxation
      Cognitive Reframing
      Worry Window
      Nature Dose
      4-7-8 Breathing
    Energy
      Ultradian Rhythm Work
      Strategic Caffeine
      Movement Snacks
      Sleep Consistency
      Energy Audit
    Focus
      Deep Work Blocks
      Task Batching
      2-Minute Rule
      Attention Residue Break
      Digital Minimalism
    Sleep
      Sleep Window
      Wind-Down Routine
      Environment Optimization
      No Caffeine After 2pm
      Worry Dump
    Pressure
      Pre-Performance Routine
      Arousal Regulation
      Process Focus
      Visualization
      After-Action Review
```
