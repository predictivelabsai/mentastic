"""
Local API simulator for mentastic-ai backend.

Mirrors all backend endpoints with mock responses so the frontend
can be developed and tested without running the real backend.

Usage:
    .venv/bin/python api/simulator.py
    # Runs on http://localhost:8181 (same port as real backend)
    # Docs at http://localhost:8181/docs
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Query, status
from fastapi.responses import StreamingResponse

from api.schemas import (
    ActionWidgets,
    ChatRequest,
    ChatResponse,
    OnboardingRequest,
    OnboardingResponse,
    StreamingEvent,
    StreamingEventData,
    StreamingEventType,
    Who5Request,
    Who5Response,
    Who5SummaryRequest,
    Who5SummaryResponse,
    WidgetInteractionRequest,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("api.simulator")

app = FastAPI(
    title="Mentastic AI API (Simulator)",
    description="Local mock of the mentastic-ai backend for frontend development",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

# session_id -> list of messages
_sessions: dict[str, list[dict]] = {}

# user_id -> WHO-5 summary
_who5_summaries: dict[str, dict] = {}

# user_id -> onboarding state (question_number)
_onboarding_state: dict[str, int] = {}

# widget interactions log
_widget_interactions: list[dict] = []

# ---------------------------------------------------------------------------
# Mock response generation
# ---------------------------------------------------------------------------

BOOTSTRAP_REPLIES = [
    "Hey! Great to see you. What's on your mind today?",
    "Hi there! How can I help you today?",
    "Hello! Ready when you are.",
]

GREETINGS = {"hi", "hello", "hey", "yo", "sup", "hola", "morning", "evening", "thanks", "thank you", "bye", "ok", "okay"}


def _is_greeting(text: str) -> bool:
    return text.strip().lower().rstrip("!.,") in GREETINGS


def _generate_reply(user_input: str, session_id: str) -> str:
    """Generate a mock assistant reply based on user input."""
    low = user_input.lower()

    if _is_greeting(low):
        import random
        return random.choice(BOOTSTRAP_REPLIES)

    if "checkin" in low or "check-in" in low or "check in" in low:
        return (
            "Let's do a quick readiness check-in. On a scale of 1-10, how would you rate:\n\n"
            "1. **Sleep quality** last night?\n"
            "2. **Energy level** right now?\n"
            "3. **Stress level** today?\n"
            "4. **Mood** overall?\n\n"
            "Take your time — there are no wrong answers."
        )

    if "report" in low:
        return (
            "Here's your latest readiness summary:\n\n"
            "- **Sleep**: 7.2/10 (improving trend)\n"
            "- **HRV**: 45ms (stable)\n"
            "- **Recovery**: 82% (good)\n"
            "- **Stress**: Low-moderate\n\n"
            "Your recovery has been consistent this week. "
            "Would you like me to dig deeper into any of these areas?"
        )

    if "sleep" in low:
        return (
            "Based on your recent patterns, your sleep has been averaging 6.8 hours "
            "with a sleep efficiency of 87%. Your deep sleep percentage is slightly "
            "below optimal. A few suggestions:\n\n"
            "1. Try to maintain a consistent bedtime\n"
            "2. Reduce screen time 30 minutes before bed\n"
            "3. Keep your room temperature around 18-19°C\n\n"
            "Would you like to set a sleep goal together?"
        )

    if "stress" in low or "anxious" in low or "anxiety" in low:
        return (
            "I hear you. Let's work through this together. "
            "Your recent HRV data suggests your nervous system has been under "
            "more load than usual.\n\n"
            "Here are a few evidence-based techniques:\n\n"
            "1. **Box breathing**: 4 seconds in, 4 hold, 4 out, 4 hold\n"
            "2. **Progressive muscle relaxation**: 5-minute body scan\n"
            "3. **Cognitive reframing**: Let's identify the thought pattern\n\n"
            "Which would you like to try right now?"
        )

    if "goal" in low or "plan" in low:
        return (
            "Setting clear goals is a great step. Let's break this down:\n\n"
            "1. **What** do you want to achieve?\n"
            "2. **Why** is this important to you right now?\n"
            "3. **When** would you like to achieve it by?\n\n"
            "Once we have these, I'll help you create an actionable plan "
            "with measurable milestones."
        )

    # Default conversational response
    return (
        f"That's an interesting point about \"{user_input[:50]}{'...' if len(user_input) > 50 else ''}\". "
        "Let me think about this from a performance and wellbeing perspective.\n\n"
        "Based on what you've shared, I'd suggest we explore this further. "
        "What specific aspect would you like to focus on? I can look at your "
        "recent data patterns or we can work through a structured approach together."
    )


# ---------------------------------------------------------------------------
# WHO-5 questionnaire flow
# ---------------------------------------------------------------------------

WHO5_QUESTIONS = [
    "Over the last two weeks, how often have you felt **cheerful and in good spirits**?",
    "Over the last two weeks, how often have you felt **calm and relaxed**?",
    "Over the last two weeks, how often have you felt **active and vigorous**?",
    "Over the last two weeks, how often have you woke up feeling **fresh and rested**?",
    "Over the last two weeks, how often has your daily life been filled with **things that interest you**?",
]

WHO5_ANSWERS = [
    "All of the time",
    "Most of the time",
    "More than half of the time",
    "Less than half of the time",
    "Some of the time",
    "At no time",
]

# session_id -> question index
_who5_state: dict[str, int] = {}


# ---------------------------------------------------------------------------
# Onboarding questionnaire flow
# ---------------------------------------------------------------------------

ONBOARDING_QUESTIONS = [
    {
        "question": "What best describes your primary goal for using Mentastic?",
        "answers": ["Improve sleep", "Manage stress", "Boost performance", "Track wellness", "Other"],
    },
    {
        "question": "How would you describe your current fitness level?",
        "answers": ["Beginner", "Intermediate", "Advanced", "Professional athlete"],
    },
    {
        "question": "Do you currently use any wearable devices?",
        "answers": ["Yes, regularly", "Sometimes", "No, but interested", "No"],
    },
]


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse_line(event: StreamingEvent) -> str:
    event_name = event.event.value
    event_data = event.data.model_dump()
    return f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"


async def _stream_reply(reply: str, session_id: str) -> AsyncGenerator[str, None]:
    """Simulate token-by-token streaming with realistic delays."""
    words = reply.split(" ")
    for i, word in enumerate(words):
        token = word if i == 0 else " " + word
        event = StreamingEvent(
            event=StreamingEventType.TOKEN,
            data=StreamingEventData(delta=token),
        )
        yield _sse_line(event)
        await asyncio.sleep(0.03)  # ~30ms per token

    # DONE event
    done_event = StreamingEvent(
        event=StreamingEventType.DONE,
        data=StreamingEventData(
            assistant_message=reply,
            session_id=session_id,
            is_safe=True,
        ),
    )
    yield _sse_line(done_event)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health Check"], status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy", "message": "Simulator is running (no database)"}


# ---------------------------------------------------------------------------
# Conversation endpoints — /v0/conversation
# ---------------------------------------------------------------------------

@app.post("/v0/conversation", response_model=ChatResponse, tags=["Conversation"], status_code=status.HTTP_200_OK)
async def chat_response(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())

    if session_id not in _sessions:
        _sessions[session_id] = []

    _sessions[session_id].append({"role": "user", "content": request.user_input})

    reply = _generate_reply(request.user_input, session_id)
    _sessions[session_id].append({"role": "assistant", "content": reply})

    logger.info("POST /v0/conversation  user=%s session=%s", request.user_id, session_id)

    return ChatResponse(
        assistant_message=reply,
        session_id=session_id,
        is_safe=True,
    )


@app.post("/v0/conversation/stream", tags=["Conversation"], status_code=status.HTTP_200_OK)
async def chat_response_streaming(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())

    if session_id not in _sessions:
        _sessions[session_id] = []

    _sessions[session_id].append({"role": "user", "content": request.user_input})

    reply = _generate_reply(request.user_input, session_id)
    _sessions[session_id].append({"role": "assistant", "content": reply})

    logger.info("POST /v0/conversation/stream  user=%s session=%s", request.user_id, session_id)

    return StreamingResponse(
        _stream_reply(reply, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )


@app.post("/v0/conversation/widget-interaction", tags=["Conversation"], status_code=status.HTTP_202_ACCEPTED)
async def save_widget_interaction(request: WidgetInteractionRequest):
    _widget_interactions.append({
        "user_id": request.user_id,
        "session_id": request.session_id,
        "action_widget": request.action_widget.value,
        "action_widget_details": request.action_widget_details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    logger.info("POST /v0/conversation/widget-interaction  user=%s widget=%s", request.user_id, request.action_widget.value)
    return None


# ---------------------------------------------------------------------------
# Questionnaire endpoints — /v0/questionnaires
# ---------------------------------------------------------------------------

@app.post("/v0/questionnaires/who5", response_model=Who5Response, tags=["Questionnaires"], status_code=status.HTTP_200_OK)
async def who5_questionnaire(request: Who5Request):
    session_id = request.session_id or str(uuid.uuid4())
    q_index = _who5_state.get(session_id, 0)

    # First call or greeting — present the first question
    if q_index == 0 and _is_greeting(request.user_input):
        _who5_state[session_id] = 0
        return Who5Response(
            assistant_message=(
                "Welcome to the WHO-5 Well-Being Index. I'll ask you 5 short questions "
                "about how you've been feeling over the last two weeks.\n\n"
                f"**Question 1/5:** {WHO5_QUESTIONS[0]}"
            ),
            is_survey_complete=False,
            session_id=session_id,
            answers=WHO5_ANSWERS,
            answer_type="SINGLE",
            is_safe=True,
        )

    # Advance to next question
    q_index += 1
    _who5_state[session_id] = q_index

    if q_index < len(WHO5_QUESTIONS):
        return Who5Response(
            assistant_message=f"**Question {q_index + 1}/5:** {WHO5_QUESTIONS[q_index]}",
            is_survey_complete=False,
            session_id=session_id,
            answers=WHO5_ANSWERS,
            answer_type="SINGLE",
            is_safe=True,
        )

    # Survey complete
    mock_score = 68.0
    del _who5_state[session_id]

    return Who5Response(
        assistant_message=(
            f"Thank you for completing the WHO-5 assessment!\n\n"
            f"Your well-being score: **{mock_score}%**\n\n"
            "This indicates a moderate level of well-being. "
            "Would you like to discuss any areas you'd like to improve?"
        ),
        is_survey_complete=True,
        session_id=session_id,
        answers=[],
        answer_type="SINGLE",
        final_score=mock_score,
        is_safe=True,
    )


@app.get("/v0/questionnaires/who5_results", response_model=Who5SummaryResponse, tags=["Questionnaires"], status_code=status.HTTP_200_OK)
async def get_who5_summary(user_id: str = Query(..., description="User ID")):
    if user_id in _who5_summaries:
        data = _who5_summaries[user_id]
        return Who5SummaryResponse(**data)

    # Return mock data for any user
    return Who5SummaryResponse(
        user_id=user_id,
        summary="Overall moderate well-being with stable patterns over the past month.",
        final_score=68.0,
        dimensions=[
            {"name": "Cheerful and in good spirits", "score": 4, "max_score": 5},
            {"name": "Calm and relaxed", "score": 3, "max_score": 5},
            {"name": "Active and vigorous", "score": 3, "max_score": 5},
            {"name": "Fresh and rested", "score": 3, "max_score": 5},
            {"name": "Interesting daily life", "score": 4, "max_score": 5},
        ],
    )


@app.post("/v0/questionnaires/who5_results", tags=["Questionnaires"], status_code=status.HTTP_200_OK)
async def save_who5_summary(request: Who5SummaryRequest):
    _who5_summaries[request.user_id] = {
        "user_id": request.user_id,
        "summary": f"WHO-5 completed on {request.completed_at.isoformat()} with score {request.final_score}%.",
        "final_score": request.final_score,
        "dimensions": [
            {"name": WHO5_QUESTIONS[i] if i < len(WHO5_QUESTIONS) else f"Dimension {i+1}", "score": s, "max_score": 5}
            for i, s in enumerate(request.dimensions)
        ],
    }
    logger.info("POST /v0/questionnaires/who5_results  user=%s score=%.1f", request.user_id, request.final_score)
    return {"message": "WHO-5 summary saved successfully"}


@app.post("/v0/questionnaires/onboarding", response_model=OnboardingResponse, tags=["Questionnaires"], status_code=status.HTTP_200_OK)
async def onboarding_questions(request: OnboardingRequest):
    session_id = request.session_id or str(uuid.uuid4())
    q_index = _onboarding_state.get(request.user_id, 0)

    # First interaction
    if q_index == 0 and _is_greeting(request.user_input):
        _onboarding_state[request.user_id] = 0
        q = ONBOARDING_QUESTIONS[0]
        return OnboardingResponse(
            assistant_message=f"Welcome! Let's get to know you a bit. {q['question']}",
            answers=q["answers"],
            answer_type="MULTIPLE",
            question_number=1,
            is_survey_complete=False,
            is_user_suitable=True,
            session_id=session_id,
        )

    q_index += 1
    _onboarding_state[request.user_id] = q_index

    if q_index < len(ONBOARDING_QUESTIONS):
        q = ONBOARDING_QUESTIONS[q_index]
        return OnboardingResponse(
            assistant_message=q["question"],
            answers=q["answers"],
            answer_type="MULTIPLE",
            question_number=q_index + 1,
            is_survey_complete=False,
            is_user_suitable=True,
            session_id=session_id,
        )

    # Complete
    del _onboarding_state[request.user_id]
    return OnboardingResponse(
        assistant_message=(
            "Thank you for completing the onboarding! "
            "Based on your responses, Mentastic is a great fit for you. "
            "Let's get started on your wellness journey."
        ),
        answers=[],
        answer_type="MULTIPLE",
        question_number=None,
        is_survey_complete=True,
        is_user_suitable=True,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.simulator:app", host="0.0.0.0", port=8181, reload=True)
