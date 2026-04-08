-- Mentastic schema: human performance and readiness platform
-- Tables: users, chat_conversations, chat_messages, readiness_checkins, session_summaries

CREATE SCHEMA IF NOT EXISTS mentastic;

-- Users
CREATE TABLE IF NOT EXISTS mentastic.users (
    id SERIAL PRIMARY KEY,
    user_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    display_name VARCHAR(255),
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mentastic_users_user_id ON mentastic.users(user_id);
CREATE INDEX IF NOT EXISTS idx_mentastic_users_email ON mentastic.users(email);

-- Chat conversations
CREATE TABLE IF NOT EXISTS mentastic.chat_conversations (
    thread_id UUID PRIMARY KEY,
    user_id UUID REFERENCES mentastic.users(user_id) ON DELETE CASCADE,
    title VARCHAR(200) DEFAULT 'New chat',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mentastic_chat_conv_user
    ON mentastic.chat_conversations(user_id);

-- Chat messages
CREATE TABLE IF NOT EXISTS mentastic.chat_messages (
    id BIGSERIAL PRIMARY KEY,
    thread_id UUID NOT NULL REFERENCES mentastic.chat_conversations(thread_id) ON DELETE CASCADE,
    message_id UUID NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mentastic_chat_msg_thread
    ON mentastic.chat_messages(thread_id, created_at);

-- Readiness check-ins (DB-backed tool)
CREATE TABLE IF NOT EXISTS mentastic.readiness_checkins (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES mentastic.users(user_id) ON DELETE CASCADE,
    energy INTEGER CHECK (energy BETWEEN 1 AND 10),
    focus INTEGER CHECK (focus BETWEEN 1 AND 10),
    stress INTEGER CHECK (stress BETWEEN 1 AND 10),
    mood INTEGER CHECK (mood BETWEEN 1 AND 10),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mentastic_checkins_user
    ON mentastic.readiness_checkins(user_id, created_at);

-- Session summaries (Patrick's memory across sessions)
CREATE TABLE IF NOT EXISTS mentastic.session_summaries (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES mentastic.users(user_id) ON DELETE CASCADE,
    thread_id UUID,
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mentastic_summaries_user
    ON mentastic.session_summaries(user_id, created_at);
