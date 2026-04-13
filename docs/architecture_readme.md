# Mentastic Architecture

Mentastic is built as a single-process server-rendered application using the **AG UI** (Agentic Graphical User Interface) pattern — a design philosophy where the AI agent is not hidden behind an API, but is the interface itself. The user interacts directly with the agent through a streaming conversational UI, while the system makes its reasoning process visible in real time.

This document describes the system architecture, the user journey, the AG UI concept, and the technical flow from landing page to agent response.

---

## User Journey

The platform follows a progressive engagement model: visitors can try Patrick anonymously on the landing page, then create an account to unlock the full experience.

```mermaid
graph LR
    subgraph "Anonymous"
        LAND[Landing Page] --> MINI[Mini-Chat<br/>with Patrick]
        MINI -->|5 messages| NUDGE[Patrick suggests<br/>creating account]
    end

    subgraph "Authentication"
        NUDGE --> CLERK[Clerk Sign-Up<br/>Email / Google / Apple]
        CLERK --> SYNC[User synced<br/>to PostgreSQL]
    end

    subgraph "Authenticated Experience"
        SYNC --> CHAT[Full 3-Pane Chat<br/>6 Tools + History]
        CHAT --> DASH[Performance<br/>Dashboard]
        CHAT --> INT[Data<br/>Integrations]
        DASH --> CHAT
        INT --> CHAT
    end
```

---

## The AG UI Concept

Traditional AI applications treat the model as a backend service: the user fills a form, the server calls an API, and a result is returned. AG UI inverts this. The agent becomes a first-class participant in the interface — it streams its thinking, shows tool calls as they happen, and the user watches the reasoning unfold token by token.

In Mentastic, this means:

- **Streaming-first interaction.** Every response from Patrick is streamed via WebSocket. The user sees tokens appear in real time, not after a loading spinner.
- **Transparent tool execution.** When Patrick calls a tool (e.g. saving a readiness check-in or generating a resilience plan), the tool call appears in the Thinking Trace panel.
- **Conversational agency.** The 6 welcome cards are conversation starters, not static forms. Clicking "My Readiness Now" sends a natural language message to Patrick, who calls the appropriate tool, analyses the data, and provides personalised insight.
- **Anonymous-first onboarding.** Visitors try Patrick directly on the landing page — no account required. After 5 messages, Patrick suggests creating an account.
- **No page reloads.** The entire interaction happens over a single WebSocket connection using HTMX out-of-band (OOB) swaps.

---

## 3-Pane Design Principles

**Left Pane (260px) — Context & Navigation.** Shows auth state, conversation history, and links to Dashboard and Integrations. Provides orientation without competing with the conversation.

**Center Pane (flexible) — Conversation.** The streaming dialogue with Patrick. The welcome screen shows 6 cards: 3 for viewing current state (My Readiness Now, Performance Overview, Stress & Load Check) and 3 for improvement actions (Readiness Check-In, Recovery Plan, Resilience Builder).

**Right Pane (380px, toggled) — Thinking Trace.** Shows the agent's internal activity: tool calls, execution status, and completion. Opens automatically during AI runs.

```mermaid
graph TB
    subgraph "App Layout (CSS Grid)"
        direction LR
        subgraph "Left Pane (260px)"
            BRAND[Mentastic + PATRICK badge]
            NEWCHAT[+ New Chat]
            CONVLIST[Conversation History]
            LINKS[Dashboard + Integrations]
            AUTH[User Info + Logout]
        end

        subgraph "Center Pane (1fr)"
            HEADER[Patrick + Trace button]
            subgraph "Chat Container (hx-ext=ws)"
                WELCOME[Welcome Screen<br/>3 State + 3 Action Cards]
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

The system is a single Python process running FastHTML. There is no separate frontend build, no API gateway, and no message queue. The browser connects via HTTP for the initial page load and then upgrades to a WebSocket for the chat session.

The LangGraph agent runs in-process, streaming events directly to the WebSocket handler. PostgreSQL stores user accounts, conversation history, and readiness check-in data. The LLM (XAI Grok) is accessed via an OpenAI-compatible API. Authentication is handled by Clerk (email, Google, Apple) with a fallback to email/password.

```mermaid
graph TB
    subgraph Browser
        UI[3-Pane FastHTML UI]
        WS[WebSocket Connection]
        HTMX[HTMX + marked.js]
        CLERK_JS[Clerk JS SDK]
    end

    subgraph "FastHTML Server (port 5010)"
        APP[app.py]
        AGUI[AGUISetup]
        THREAD[AGUIThread]
        UIC[UI Renderer]
        ANON[Anonymous WS Handler]
    end

    subgraph "LangGraph Agent"
        AGENT[ReAct Agent]
        LLM[XAI Grok LLM]
        TOOLS[6 Tools]
    end

    subgraph "External Services"
        CLERK_API[Clerk API<br/>Auth + JWKS]
        ARCADE[arcade.dev<br/>composio.dev]
    end

    subgraph "PostgreSQL (mentastic schema)"
        USERS[(users)]
        CONV[(chat_conversations)]
        MSGS[(chat_messages)]
        CHECKINS[(readiness_checkins)]
        SUMMARIES[(session_summaries)]
    end

    UI -->|HTTP GET| APP
    UI -->|WS /agui/ws/| WS
    UI -->|WS /anon-ws/| ANON
    CLERK_JS -->|JWT| CLERK_API
    WS --> AGUI
    AGUI --> THREAD
    THREAD --> UIC
    THREAD -->|astream_events v2| AGENT
    ANON -->|astream_events v2| AGENT
    AGENT --> LLM
    AGENT --> TOOLS
    TOOLS -->|DB-backed| CHECKINS
    THREAD -->|save| MSGS
    THREAD -->|save| CONV
    APP -->|verify JWT| CLERK_API
    APP -->|sync user| USERS
    APP -.->|future| ARCADE
    LLM -->|streaming tokens| THREAD
    THREAD -->|OOB swap HTML| WS
```

---

## WebSocket Streaming Flow

When a user sends a message, the following sequence occurs — all within a single WebSocket connection:

1. The user's message is immediately rendered as a chat bubble (optimistic UI).
2. An empty assistant bubble is created with a streaming cursor.
3. The LangGraph agent begins processing, and events are streamed back.
4. Each token is appended to the assistant bubble in real time via HTMX OOB swap.
5. If the agent calls a tool, it appears in both the chat and the Thinking Trace panel.
6. When complete, raw text is replaced with server-side rendered markdown.

Time to first token: ~0.5 seconds. Full response: ~2-3 seconds.

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
    T->>B: Trace: "Patrick is thinking..."
    T->>DB: save_message(user msg)

    T->>A: astream_events(messages, v2)

    loop Token Streaming
        A->>L: Chat completion (streaming)
        L-->>A: Token chunk
        A-->>T: on_chat_model_stream event
        T->>B: Span token (OOB beforeend)
    end

    opt Tool Call
        A-->>T: on_tool_start event
        T->>B: Tool indicator in chat + trace
        A->>A: Execute tool
        A-->>T: on_tool_end event
        T->>B: Update tool status (OOB)
    end

    T->>B: Server-rendered markdown (OOB outerHTML)
    T->>DB: save_message(assistant response)
    T->>B: Re-enable input, refresh conversation list
```

---

## Agent Architecture

Patrick uses LangGraph's `create_react_agent` — a ReAct (Reasoning + Acting) agent. The 6 tools are split into two categories:

**DB-backed tools** persist data and query patterns. The readiness check-in saves energy/focus/stress/mood (1-10) to PostgreSQL. The readiness report aggregates check-ins and detects trends.

**Conversational tools** return structured frameworks that Patrick weaves into personalised dialogue. The same recovery plan tool produces different conversations depending on the user's context.

The LLM model is configurable via `MODEL_NAME` (default: `grok-4-fast-reasoning`). The agent is created per-thread and cached.

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

## Authentication Flow

Mentastic supports two auth modes: **Clerk** (email, Google, Apple) and **fallback** (email/password). When Clerk is configured, the sign-in/sign-up pages mount Clerk's prebuilt UI components. The backend verifies Clerk JWTs via their JWKS endpoint and syncs user data to the local PostgreSQL database.

```mermaid
sequenceDiagram
    participant U as User
    participant B as Browser
    participant CK as Clerk JS
    participant API as Clerk API
    participant S as FastHTML Server
    participant DB as PostgreSQL

    U->>B: Click "Get Started"
    B->>CK: Mount SignUp component
    U->>CK: Enter email / click Google / Apple
    CK->>API: Authenticate
    API-->>CK: Session JWT (__session cookie)
    CK->>B: Redirect to /chat
    B->>S: GET /chat (with __session cookie)
    S->>API: Verify JWT via JWKS
    API-->>S: Valid (user_id, email)
    S->>DB: Upsert user in mentastic.users
    S-->>B: Render 3-pane chat
```

---

## Dashboard

The performance dashboard shows mock data styled like Apple/Google fitness apps. In production, this data comes from readiness check-ins and connected integrations. Charts are rendered as inline SVG — no JavaScript chart libraries.

```mermaid
graph TB
    subgraph "Dashboard Layout"
        direction TB
        KPI[4 KPI Cards<br/>Readiness · Energy · Stress · Sleep]
        subgraph "Charts Row 1"
            BAR1[Readiness Bar Chart<br/>Green/Yellow coded]
            BAR2[Energy vs Stress<br/>Comparison bars]
        end
        subgraph "Charts Row 2"
            RING[Time Distribution<br/>Donut chart]
            BAR3[Sleep & Activity<br/>Bars + step counts]
        end
        INSIGHTS[Patrick's Insights<br/>Personalised analysis]
    end

    KPI --> BAR1
    KPI --> BAR2
    BAR1 --> RING
    BAR2 --> BAR3
    RING --> INSIGHTS
    BAR3 --> INSIGHTS
```

---

## Data Integrations

Mentastic connects to 16 data sources via three integration providers:

- **[Thryve Health](https://thryve.health)** — Unified wearable hub providing access to 500+ devices through a single API. Delivers 18 data categories (sleep, HR, HRV, activity, body composition, blood glucose, respiratory, VO2max) plus analytics: sleep quality scoring, fitness age calculation, and mental health risk assessment. Thryve handles device authorization, real-time data sync, and data normalization.
- **[arcade.dev](https://arcade.dev)** — OAuth-based integrations for Google Fit, Apple Health, Google Calendar, Spotify, Slack.
- **[composio.dev](https://composio.dev)** — Oura Ring, Garmin, Strava, and other wearable-specific integrations.

```mermaid
graph TB
    subgraph "Thryve Health — Unified Hub (500+ devices)"
        TH_API[Thryve API<br/>18 data categories · Analytics]
        TH_FIT[Fitbit] --> TH_API
        TH_WI[Withings] --> TH_API
        TH_PO[Polar] --> TH_API
        TH_WH[Whoop] --> TH_API
        TH_SU[Suunto] --> TH_API
        TH_SA[Samsung Health] --> TH_API
        TH_DX[Dexcom CGM] --> TH_API
    end

    subgraph "Direct Integrations"
        ARC[arcade.dev]
        COM[composio.dev]
        GF[Google Fit] --> ARC
        AH[Apple Health] --> ARC
        GC[Google Calendar] --> ARC
        SP_I[Spotify] --> ARC
        OR[Oura Ring] --> COM
        GA[Garmin] --> COM
    end

    subgraph "Coming Soon"
        ST[Strava] --> COM
        SL[Slack] --> ARC
    end

    TH_API --> MENTASTIC[Mentastic<br/>Patrick AI Agent]
    ARC --> MENTASTIC
    COM --> MENTASTIC

    subgraph "Thryve Analytics"
        SQ[Sleep Quality Scoring]
        FA[Fitness Age / VO2max]
        MH[Mental Health Risk]
    end

    TH_API --> SQ
    TH_API --> FA
    TH_API --> MH
    SQ --> MENTASTIC
    FA --> MENTASTIC
    MH --> MENTASTIC
```

Each integration has a connection flow: detail page (what data is accessed, privacy info) → confirm → connected state with disconnect option.

---

## Database Schema

5 tables in the `mentastic` schema. No ORM models — all queries use raw SQL via SQLAlchemy's `text()`.

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

Single Docker container on Coolify at `mentastic.predictivelabs.ai`. PostgreSQL, XAI API, and Clerk are external services.

```mermaid
graph LR
    subgraph "Coolify (mentastic.predictivelabs.ai)"
        DOCKER[Docker Container<br/>python:3.13-slim]
        APP[app.py :5010]
    end

    subgraph "External"
        PG[(PostgreSQL<br/>mentastic schema)]
        XAI[XAI API<br/>api.x.ai/v1]
        CK[Clerk API<br/>Auth + JWKS]
        ARC[arcade.dev<br/>composio.dev]
    end

    DOCKER --> APP
    APP -->|DB_URL| PG
    APP -->|XAI_API_KEY| XAI
    APP -->|CLERK keys| CK
    APP -.->|future| ARC

    USER[Browser] -->|HTTPS| DOCKER
    USER -->|WSS| DOCKER
```

---

## Resilience Builder: Tool Detail

30 evidence-based exercises across 6 focus areas. Patrick selects the appropriate set based on the user's request and adapts presentation to the individual.

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
