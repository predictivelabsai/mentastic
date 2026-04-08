# Mentastic Architecture

## System Overview

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

## WebSocket Streaming Flow

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

    T->>B: Remove streaming cursor
    T->>B: Trace: "Response complete"
    T->>DB: save_message(assistant response)
    T->>B: Re-enable input + render markdown
    T->>B: Refresh conversation list (OOB)
```

## Agent Architecture

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

## 3-Pane UI Layout

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

## Database Schema

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

## Deployment

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

## Tool Detail: Resilience Builder Focus Areas

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
