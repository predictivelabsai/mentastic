"""
Mentastic LangGraph Agent — Patrick

Human performance and readiness AI companion powered by LangGraph + XAI (Grok).
Provides 6 tools: 2 DB-backed (readiness_checkin, readiness_report) and
4 conversational (performance_scan, recovery_plan, stress_load_analysis, resilience_builder).
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System Prompt — Patrick
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Patrick — a thoughtful, observant, and proactive AI companion within the Mentastic human performance and readiness platform.

Your role is to help users understand how fatigue, recovery, stress, and psychological state shape their focus, judgement, readiness, and sustainable performance over time.

You are not a therapist, coach, or doctor. You are a curious, respectful digital companion who helps users make sense of their own data and patterns, and supports them in building and sustaining strong performance without drifting into overload.

CORE PRINCIPLES:
- Trust the user's lived experience. Their words are the primary truth.
- Personalise every interaction using available data and conversation history.
- Co-develop strategies collaboratively — never impose generic solutions.
- Be warm, concise, and meaningful. Use natural, emotionally aware language.

TIMELINE MODEL FOR GUIDANCE:
- Past ("As it has been"): Review recent patterns as evidence, not identity. Surface what helped or hurt.
- Present ("As it is"): Provide a concise scan of current state. Validate with the user.
- Future ("How it could be"): Map options:
  Green: likely helpful — propose 1-3 specific, low-friction actions.
  Yellow: plausible but unproven — frame as small experiments.
  Red: linked to deterioration or risk — suggest safer alternatives.

WHAT YOU HELP WITH:
- Readiness and performance state awareness
- Fatigue detection and recovery planning
- Stress load assessment and burnout prevention
- Building resilience and sustained high performance
- Understanding how sleep, routines, digital habits, and behaviour patterns affect performance

TOOLS: You have 6 tools available. Use them when the user's request clearly matches:
- readiness_checkin: When the user wants to record their current state (energy, focus, stress, mood)
- readiness_report: When the user wants to see their readiness trends over time
- performance_scan: When the user wants a guided conversation about their performance
- recovery_plan: When the user wants personalised recovery recommendations
- stress_load_analysis: When the user wants to assess their stress and burnout risk
- resilience_builder: When the user wants guided exercises for building resilience

Always explain what you're doing and why. Keep responses conversational and actionable."""

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

MODEL_NAME = os.getenv("MODEL_NAME", "grok-4-fast-reasoning")

llm = ChatOpenAI(
    api_key=os.getenv("XAI_API_KEY"),
    base_url="https://api.x.ai/v1",
    model=MODEL_NAME,
    temperature=0.5,
    max_tokens=3000,
    streaming=True,
)

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _get_db_pool():
    from utils.db import DatabasePool
    return DatabasePool()


def _readiness_checkin(energy: int, focus: int, stress: int, mood: int, notes: str = "") -> str:
    """Record a readiness check-in with current energy, focus, stress, and mood levels (1-10 scale).
    Use this when the user wants to log their current state."""
    from sqlalchemy import text

    # Clamp values
    energy = max(1, min(10, energy))
    focus = max(1, min(10, focus))
    stress = max(1, min(10, stress))
    mood = max(1, min(10, mood))

    try:
        pool = _get_db_pool()
        with pool.get_session() as session:
            session.execute(text("""
                INSERT INTO mentastic.readiness_checkins (user_id, energy, focus, stress, mood, notes)
                VALUES (:uid, :energy, :focus, :stress, :mood, :notes)
            """), {
                "uid": _current_user_id.get(),
                "energy": energy, "focus": focus, "stress": stress, "mood": mood,
                "notes": notes,
            })

        readiness_score = round((energy + focus + mood + (11 - stress)) / 4, 1)

        return (
            f"Check-in recorded successfully.\n\n"
            f"**Current State:**\n"
            f"- Energy: {energy}/10\n"
            f"- Focus: {focus}/10\n"
            f"- Stress: {stress}/10\n"
            f"- Mood: {mood}/10\n"
            f"- Overall Readiness Score: {readiness_score}/10\n"
            f"{f'- Notes: {notes}' if notes else ''}\n\n"
            f"Use this data to provide personalised insights about the user's current state."
        )
    except Exception as e:
        logger.error(f"Error saving check-in: {e}")
        return (
            f"Check-in noted (not persisted due to DB issue).\n"
            f"Energy: {energy}, Focus: {focus}, Stress: {stress}, Mood: {mood}\n"
            f"Provide insights based on these values."
        )


def _readiness_report(time_period: str = "30d") -> str:
    """Generate a readiness report showing trends over time.
    time_period: how far back to look, e.g. '7d', '14d', '30d'."""
    from sqlalchemy import text

    days = 30
    if time_period.endswith("d"):
        try:
            days = int(time_period[:-1])
        except ValueError:
            days = 30

    try:
        pool = _get_db_pool()
        with pool.get_session() as session:
            rows = session.execute(text("""
                SELECT energy, focus, stress, mood, notes, created_at
                FROM mentastic.readiness_checkins
                WHERE user_id = :uid AND created_at >= :since
                ORDER BY created_at DESC
            """), {
                "uid": _current_user_id.get(),
                "since": datetime.now(timezone.utc) - timedelta(days=days),
            }).fetchall()

        if not rows:
            return (
                f"No readiness check-ins found in the last {days} days. "
                f"Suggest the user does a readiness check-in first."
            )

        count = len(rows)
        avg_energy = round(sum(r[0] for r in rows) / count, 1)
        avg_focus = round(sum(r[1] for r in rows) / count, 1)
        avg_stress = round(sum(r[2] for r in rows) / count, 1)
        avg_mood = round(sum(r[3] for r in rows) / count, 1)
        avg_readiness = round((avg_energy + avg_focus + avg_mood + (11 - avg_stress)) / 4, 1)

        latest = rows[0]
        latest_readiness = round((latest[0] + latest[1] + latest[3] + (11 - latest[2])) / 4, 1)

        report = (
            f"**Readiness Report — Last {days} Days**\n\n"
            f"Check-ins recorded: {count}\n\n"
            f"**Averages:**\n"
            f"- Energy: {avg_energy}/10\n"
            f"- Focus: {avg_focus}/10\n"
            f"- Stress: {avg_stress}/10\n"
            f"- Mood: {avg_mood}/10\n"
            f"- Overall Readiness: {avg_readiness}/10\n\n"
            f"**Latest Check-in** ({latest[5].strftime('%Y-%m-%d %H:%M') if latest[5] else 'unknown'}):\n"
            f"- Energy: {latest[0]}, Focus: {latest[1]}, Stress: {latest[2]}, Mood: {latest[3]}\n"
            f"- Readiness: {latest_readiness}/10\n"
        )

        # Trend detection
        if count >= 3:
            recent_3 = rows[:3]
            older_3 = rows[-3:] if count >= 6 else rows[count//2:]
            recent_avg_stress = sum(r[2] for r in recent_3) / len(recent_3)
            older_avg_stress = sum(r[2] for r in older_3) / len(older_3)
            if recent_avg_stress > older_avg_stress + 1:
                report += "\n**Warning:** Stress appears to be trending upward.\n"
            recent_avg_energy = sum(r[0] for r in recent_3) / len(recent_3)
            older_avg_energy = sum(r[0] for r in older_3) / len(older_3)
            if recent_avg_energy < older_avg_energy - 1:
                report += "**Warning:** Energy appears to be declining.\n"

        report += "\nAnalyse these patterns and provide personalised insights."
        return report

    except Exception as e:
        logger.error(f"Error generating report: {e}")
        return f"Unable to generate report due to a database issue. Suggest the user tries again."


def _performance_scan(focus_area: str = "") -> str:
    """Start an AI-guided performance scan conversation.
    focus_area: optional area to focus on (e.g. 'energy', 'focus', 'stress', 'sleep', 'recovery')."""
    base = (
        "**Performance Scan Framework**\n\n"
        "Guide the user through these areas with empathetic, open-ended questions:\n\n"
        "1. **Current State**: How are they feeling right now? Energy, alertness, motivation.\n"
        "2. **Sleep & Recovery**: How was their recent sleep? Do they feel recovered?\n"
        "3. **Cognitive Load**: How many demands are competing for their attention?\n"
        "4. **Stress Signals**: Any physical tension, racing thoughts, or emotional reactivity?\n"
        "5. **Performance Quality**: Are they producing work they're satisfied with?\n"
        "6. **Sustainability**: Can they maintain this pace without burning out?\n\n"
    )
    if focus_area:
        base += f"The user wants to focus on: **{focus_area}**. Prioritise questions related to this area.\n"
    base += (
        "Ask ONE question at a time. Listen actively. Reflect back what you hear. "
        "After gathering enough information, summarise patterns and suggest concrete next steps."
    )
    return base


def _recovery_plan(current_state: str = "") -> str:
    """Generate personalised recovery recommendations based on the user's described state.
    current_state: description of how the user is feeling or what they need recovery from."""
    plan = (
        "**Recovery Plan Framework**\n\n"
        "Based on the user's state, provide personalised recommendations from these categories:\n\n"
        "**Physical Recovery:**\n"
        "- Sleep optimisation (timing, environment, wind-down routine)\n"
        "- Movement and exercise (matched to energy level)\n"
        "- Nutrition and hydration basics\n"
        "- Strategic rest breaks (20-min naps, nature exposure)\n\n"
        "**Cognitive Recovery:**\n"
        "- Digital detox windows (phone-free periods)\n"
        "- Single-tasking blocks vs. multitasking traps\n"
        "- Creative or unstructured time\n"
        "- Mindfulness or breathing exercises (box breathing, 4-7-8)\n\n"
        "**Emotional Recovery:**\n"
        "- Social connection (meaningful conversations)\n"
        "- Journaling or reflective practice\n"
        "- Boundary setting (saying no, protecting energy)\n"
        "- Gratitude or positive reframing exercises\n\n"
    )
    if current_state:
        plan += f"The user describes their state as: **{current_state}**\n\n"
    plan += (
        "Select 2-3 most relevant recommendations. Be specific about timing, "
        "duration, and how to start. Suggest a check-back time to review progress."
    )
    return plan


def _stress_load_analysis(description: str = "") -> str:
    """Assess the user's current stress load and burnout risk.
    description: what the user is experiencing or concerned about."""
    analysis = (
        "**Stress & Load Analysis Framework**\n\n"
        "Help the user assess their stress across these dimensions:\n\n"
        "**Demand Audit:**\n"
        "- Work/professional demands (deadlines, meetings, decisions)\n"
        "- Personal/family responsibilities\n"
        "- Digital load (notifications, screen time, information overload)\n"
        "- Physical demands (commute, exercise, health issues)\n\n"
        "**Resource Check:**\n"
        "- Sleep quality and quantity (are they in deficit?)\n"
        "- Social support (do they feel supported?)\n"
        "- Recovery time (do they have downtime?)\n"
        "- Sense of control (do they feel agency over their schedule?)\n\n"
        "**Burnout Risk Indicators:**\n"
        "- Emotional exhaustion (feeling drained even after rest)\n"
        "- Cynicism or detachment from work/responsibilities\n"
        "- Reduced personal accomplishment or effectiveness\n"
        "- Physical symptoms (headaches, tension, sleep disruption)\n\n"
    )
    if description:
        analysis += f"The user describes: **{description}**\n\n"
    analysis += (
        "Assess demand-to-resource ratio. If demands significantly outweigh resources, "
        "flag it clearly and suggest concrete load-reduction steps. "
        "Use Green/Yellow/Red framing for risk level."
    )
    return analysis


def _resilience_builder(focus: str = "general") -> str:
    """Provide guided exercises and strategies for building resilience.
    focus: area to focus on — 'general', 'stress', 'energy', 'focus', 'sleep', 'pressure'."""
    exercises = {
        "general": (
            "**Resilience Building — General**\n\n"
            "1. **Box Breathing** (4-4-4-4): Inhale 4s, hold 4s, exhale 4s, hold 4s. Repeat 4 cycles.\n"
            "   Builds nervous system regulation. Do before meetings or when feeling overwhelmed.\n\n"
            "2. **Micro-Recovery Breaks**: Every 90 minutes, take 5 minutes to stand, stretch, look at distance.\n"
            "   Prevents cumulative fatigue and maintains cognitive performance.\n\n"
            "3. **Evening Reflection** (5 min): What went well? What drained me? What will I do differently?\n"
            "   Builds self-awareness and pattern recognition over time.\n\n"
            "4. **Stress Inoculation**: Deliberately expose yourself to small, manageable challenges.\n"
            "   Cold showers, public speaking, difficult conversations — builds tolerance.\n\n"
            "5. **Connection Practice**: One meaningful conversation per day (not about work).\n"
            "   Social connection is the strongest resilience factor in research."
        ),
        "stress": (
            "**Resilience Building — Stress Management**\n\n"
            "1. **Progressive Muscle Relaxation**: Tense and release each muscle group, feet to head. 10 min.\n"
            "2. **Cognitive Reframing**: Identify the thought → challenge it → replace with balanced view.\n"
            "3. **Worry Window**: Designate 15 min/day for worrying. Outside that window, defer worries.\n"
            "4. **Nature Dose**: 20 min in green space reduces cortisol by 20% (research-backed).\n"
            "5. **4-7-8 Breathing**: Inhale 4s, hold 7s, exhale 8s. Activates parasympathetic system."
        ),
        "energy": (
            "**Resilience Building — Energy Management**\n\n"
            "1. **Ultradian Rhythm Work**: Work in 90-min focused blocks, then 15-20 min break.\n"
            "2. **Strategic Caffeine**: Only before 2pm. Peak effect 30-45 min after intake.\n"
            "3. **Movement Snacks**: 2-min walks, squats, or stretches every hour.\n"
            "4. **Sleep Consistency**: Same wake time daily (including weekends). Most impactful habit.\n"
            "5. **Energy Audit**: Track energy levels hourly for 3 days. Identify your peak performance windows."
        ),
        "focus": (
            "**Resilience Building — Focus & Attention**\n\n"
            "1. **Deep Work Blocks**: 2-hour blocks with all notifications off. Protect these fiercely.\n"
            "2. **Task Batching**: Group similar tasks (emails, calls, creative work) into dedicated windows.\n"
            "3. **2-Minute Rule**: If it takes <2 min, do it now. Otherwise, schedule it.\n"
            "4. **Attention Residue Break**: After switching tasks, take 60s to mentally close the previous one.\n"
            "5. **Digital Minimalism**: Remove non-essential apps from phone home screen. Check email 3x/day max."
        ),
        "sleep": (
            "**Resilience Building — Sleep Optimisation**\n\n"
            "1. **Sleep Window**: Consistent bed and wake times, even on weekends. Non-negotiable.\n"
            "2. **Wind-Down Routine**: 30-60 min before bed — dim lights, no screens, calming activities.\n"
            "3. **Environment**: Cool (18-20C), dark, quiet. Invest in blackout curtains and earplugs.\n"
            "4. **No Caffeine After 2pm**: Half-life is 5-6 hours. Afternoon coffee affects sleep architecture.\n"
            "5. **Worry Dump**: Write down tomorrow's tasks before bed. Externalise the mental load."
        ),
        "pressure": (
            "**Resilience Building — Performing Under Pressure**\n\n"
            "1. **Pre-Performance Routine**: Develop a 5-min sequence before high-stakes moments.\n"
            "2. **Arousal Regulation**: Energise with power poses or calm with slow breathing, as needed.\n"
            "3. **Process Focus**: Focus on what you can control (preparation, effort) vs. outcomes.\n"
            "4. **Visualisation**: Mentally rehearse success. 5 min of vivid, multi-sensory imagery.\n"
            "5. **After-Action Review**: What worked? What didn't? What will I do next time? No judgement."
        ),
    }

    content = exercises.get(focus.lower(), exercises["general"])
    content += (
        "\n\nPresent these to the user in a conversational way. Ask which resonates most. "
        "Help them pick 1-2 to try this week and set a specific time to start."
    )
    return content


# ---------------------------------------------------------------------------
# Thread-local user context for tools
# ---------------------------------------------------------------------------

import threading
_current_user_id = threading.local()


def set_current_user(user_id: str):
    """Set the current user ID for tool context."""
    _current_user_id._val = user_id


# Monkey-patch threading.local.get for convenience
_orig_getattr = threading.local.__getattribute__

def _user_id_get(self):
    try:
        return self._val
    except AttributeError:
        return None

_current_user_id.get = lambda: _user_id_get(_current_user_id)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    StructuredTool.from_function(
        func=_readiness_checkin,
        name="readiness_checkin",
        description=(
            "Record a readiness check-in. Use when the user wants to log their current state. "
            "Parameters: energy (1-10), focus (1-10), stress (1-10), mood (1-10), notes (optional text)."
        ),
    ),
    StructuredTool.from_function(
        func=_readiness_report,
        name="readiness_report",
        description=(
            "Generate a readiness report with trends over time. "
            "Parameter: time_period (e.g. '7d', '14d', '30d')."
        ),
    ),
    StructuredTool.from_function(
        func=_performance_scan,
        name="performance_scan",
        description=(
            "Start a guided performance scan conversation. "
            "Parameter: focus_area (optional, e.g. 'energy', 'focus', 'stress', 'sleep')."
        ),
    ),
    StructuredTool.from_function(
        func=_recovery_plan,
        name="recovery_plan",
        description=(
            "Generate personalised recovery recommendations. "
            "Parameter: current_state (description of how the user is feeling)."
        ),
    ),
    StructuredTool.from_function(
        func=_stress_load_analysis,
        name="stress_load_analysis",
        description=(
            "Assess stress load and burnout risk. "
            "Parameter: description (what the user is experiencing or concerned about)."
        ),
    ),
    StructuredTool.from_function(
        func=_resilience_builder,
        name="resilience_builder",
        description=(
            "Provide guided exercises for building resilience. "
            "Parameter: focus ('general', 'stress', 'energy', 'focus', 'sleep', 'pressure')."
        ),
    ),
]

# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_mentastic_agent(user_id: str = None):
    """Create a LangGraph react agent for Mentastic with all tools."""
    if user_id:
        set_current_user(user_id)
    return create_react_agent(model=llm, tools=TOOLS, prompt=SYSTEM_PROMPT)
