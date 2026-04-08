"""
Mentastic Test Suite

Covers: DB connection, schema, auth, chat store, agent tools, config.

Run: python tests/test_suite.py
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

_results = []
_pass = 0
_fail = 0


def test(name):
    def decorator(fn):
        fn._test_name = name
        return fn
    return decorator


def run_test(fn):
    global _pass, _fail
    name = getattr(fn, "_test_name", fn.__name__)
    try:
        result = fn()
        _pass += 1
        _results.append({"test": name, "status": "PASS", "result": str(result)[:200]})
        print(f"  PASS  {name}")
    except Exception as e:
        _fail += 1
        _results.append({"test": name, "status": "FAIL", "error": str(e)[:200]})
        print(f"  FAIL  {name}: {e}")


def save_results(filename, results):
    out_dir = Path(__file__).parent.parent / "test-data"
    out_dir.mkdir(exist_ok=True)
    with open(out_dir / filename, "w") as f:
        json.dump(results, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

print("\n=== Mentastic Test Suite ===\n")

# --- DB ---
print("DB Tests:")

@test("DB connection")
def test_db_connection():
    from utils.db import DatabasePool
    from sqlalchemy import text
    pool = DatabasePool()
    with pool.get_session() as s:
        result = s.execute(text("SELECT 1")).scalar()
    assert result == 1
    return "Connected"

run_test(test_db_connection)

@test("Schema exists")
def test_schema_exists():
    from utils.db import DatabasePool
    from sqlalchemy import text
    pool = DatabasePool()
    with pool.get_session() as s:
        result = s.execute(text(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'mentastic'"
        )).fetchone()
    assert result is not None, "mentastic schema not found"
    return "Schema exists"

run_test(test_schema_exists)

@test("Users table exists")
def test_users_table():
    from utils.db import DatabasePool
    from sqlalchemy import text
    pool = DatabasePool()
    with pool.get_session() as s:
        result = s.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'mentastic' AND table_name = 'users'"
        )).fetchone()
    assert result is not None, "mentastic.users table not found"
    return "Users table OK"

run_test(test_users_table)

@test("All 5 tables exist")
def test_all_tables():
    from utils.db import DatabasePool
    from sqlalchemy import text
    pool = DatabasePool()
    expected = {"users", "chat_conversations", "chat_messages", "readiness_checkins", "session_summaries"}
    with pool.get_session() as s:
        rows = s.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'mentastic'"
        )).fetchall()
    found = {r[0] for r in rows}
    missing = expected - found
    assert not missing, f"Missing tables: {missing}"
    return f"All {len(expected)} tables present"

run_test(test_all_tables)

# --- Auth ---
print("\nAuth Tests:")

@test("Password hashing")
def test_password_hash():
    from utils.auth import hash_password, verify_password
    h = hash_password("testpass123")
    assert verify_password("testpass123", h)
    assert not verify_password("wrongpass", h)
    return "Hash/verify works"

run_test(test_password_hash)

@test("JWT encode/decode")
def test_jwt():
    from utils.auth import create_jwt_token, decode_jwt_token
    token = create_jwt_token("test-user-id", "test@example.com")
    payload = decode_jwt_token(token)
    assert payload is not None
    assert payload["user_id"] == "test-user-id"
    assert payload["email"] == "test@example.com"
    return "JWT works"

run_test(test_jwt)

@test("User creation and authentication")
def test_user_crud():
    from utils.auth import create_user, authenticate, get_user_by_email
    from utils.db import DatabasePool
    from sqlalchemy import text
    # Clean up test user if exists
    pool = DatabasePool()
    with pool.get_session() as s:
        s.execute(text("DELETE FROM mentastic.users WHERE email = 'test_suite@mentastic.test'"))
    # Create
    user = create_user("test_suite@mentastic.test", "testpass123", "Test User")
    assert user is not None, "create_user returned None"
    assert user["email"] == "test_suite@mentastic.test"
    # Authenticate
    authed = authenticate("test_suite@mentastic.test", "testpass123")
    assert authed is not None, "authenticate returned None"
    assert authed["display_name"] == "Test User"
    # Wrong password
    bad = authenticate("test_suite@mentastic.test", "wrongpass")
    assert bad is None, "Wrong password should fail"
    # Cleanup
    with pool.get_session() as s:
        s.execute(text("DELETE FROM mentastic.users WHERE email = 'test_suite@mentastic.test'"))
    return "User CRUD works"

run_test(test_user_crud)

# --- Chat Store ---
print("\nChat Store Tests:")

@test("Save and load conversation")
def test_chat_store():
    import uuid
    from utils.chat_store import save_conversation, save_message, load_conversation_messages, delete_conversation
    tid = str(uuid.uuid4())
    save_conversation(tid, title="Test Chat")
    save_message(tid, "user", "Hello Patrick")
    save_message(tid, "assistant", "Hello! How can I help?")
    msgs = load_conversation_messages(tid)
    assert len(msgs) == 2, f"Expected 2 messages, got {len(msgs)}"
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    delete_conversation(tid)
    msgs2 = load_conversation_messages(tid)
    assert len(msgs2) == 0, "Messages should be deleted"
    return "Chat store works"

run_test(test_chat_store)

# --- Agent ---
print("\nAgent Tests:")

@test("Agent tools loaded")
def test_agent_tools():
    from utils.agent import TOOLS
    names = [t.name for t in TOOLS]
    expected = ["readiness_checkin", "readiness_report", "performance_scan",
                "recovery_plan", "stress_load_analysis", "resilience_builder"]
    assert names == expected, f"Expected {expected}, got {names}"
    return f"6 tools: {names}"

run_test(test_agent_tools)

@test("System prompt configured")
def test_system_prompt():
    from utils.agent import SYSTEM_PROMPT
    assert "Patrick" in SYSTEM_PROMPT
    assert "performance" in SYSTEM_PROMPT.lower()
    assert "readiness" in SYSTEM_PROMPT.lower()
    assert len(SYSTEM_PROMPT) > 500
    return f"Prompt length: {len(SYSTEM_PROMPT)} chars"

run_test(test_system_prompt)

@test("LLM model configured")
def test_llm_config():
    from utils.agent import MODEL_NAME, llm
    assert MODEL_NAME == os.getenv("MODEL_NAME", "grok-4-fast-reasoning")
    assert llm is not None
    return f"Model: {MODEL_NAME}"

run_test(test_llm_config)

@test("Agent factory creates agent")
def test_agent_factory():
    from utils.agent import create_mentastic_agent
    agent = create_mentastic_agent("test-user-id")
    assert agent is not None
    return "Agent created"

run_test(test_agent_factory)

@test("Conversational tool: performance_scan")
def test_performance_scan():
    from utils.agent import _performance_scan
    result = _performance_scan("energy")
    assert "Performance Scan" in result
    assert "energy" in result.lower()
    return "performance_scan works"

run_test(test_performance_scan)

@test("Conversational tool: recovery_plan")
def test_recovery_plan():
    from utils.agent import _recovery_plan
    result = _recovery_plan("feeling exhausted")
    assert "Recovery Plan" in result
    assert "exhausted" in result
    return "recovery_plan works"

run_test(test_recovery_plan)

@test("Conversational tool: stress_load_analysis")
def test_stress_load_analysis():
    from utils.agent import _stress_load_analysis
    result = _stress_load_analysis("work deadlines piling up")
    assert "Stress" in result
    assert "deadlines" in result
    return "stress_load_analysis works"

run_test(test_stress_load_analysis)

@test("Conversational tool: resilience_builder")
def test_resilience_builder():
    from utils.agent import _resilience_builder
    result = _resilience_builder("stress")
    assert "Resilience" in result
    assert "Stress" in result
    return "resilience_builder works"

run_test(test_resilience_builder)

@test("Resilience builder focus areas")
def test_resilience_areas():
    from utils.agent import _resilience_builder
    for area in ["general", "stress", "energy", "focus", "sleep", "pressure"]:
        result = _resilience_builder(area)
        assert "Resilience" in result, f"Missing title for {area}"
    return "All 6 focus areas work"

run_test(test_resilience_areas)

# --- Config ---
print("\nConfig Tests:")

@test("Environment variables set")
def test_env_vars():
    assert os.getenv("DB_URL"), "DB_URL not set"
    assert os.getenv("XAI_API_KEY"), "XAI_API_KEY not set"
    assert os.getenv("MODEL_NAME"), "MODEL_NAME not set"
    return "Env vars OK"

run_test(test_env_vars)

@test("App imports successfully")
def test_app_imports():
    from app import app, agui
    assert app is not None
    assert agui is not None
    return "App imports OK"

run_test(test_app_imports)

# --- Summary ---
print(f"\n{'='*40}")
print(f"Results: {_pass} passed, {_fail} failed, {_pass + _fail} total")
print(f"{'='*40}\n")

save_results("test_summary.json", {
    "total": _pass + _fail,
    "passed": _pass,
    "failed": _fail,
    "tests": _results,
})

sys.exit(0 if _fail == 0 else 1)
