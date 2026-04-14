"""Pydantic schemas mirroring the mentastic-ai backend API contracts."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum
from datetime import datetime


# --- Enums ---

class ActionWidgets(str, Enum):
    MOOD_CHECK_IN = "MCI"
    SUMMARY = "SUMMARY"
    MCI_GRAPH = "MCI_GRAPH"
    QUESTIONNAIRE = "QUESTIONNAIRE"


class StreamingEventType(str, Enum):
    TOKEN = "TOKEN"
    DONE = "DONE"
    ERROR = "ERROR"


# --- Conversation schemas ---

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    user_input: str = Field(..., description="User's input message")
    user_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    system_prompt_from_admin: bool = Field(False)
    intent: Optional[str] = Field(None)
    starter_prompt: bool = Field(False)
    llm_provider: str = Field("openai")
    llm_model: str = Field("gpt-5.2")


class ChatResponse(BaseModel):
    assistant_message: str
    session_id: str
    is_safe: bool
    questionnaire_id: Optional[int] = None
    action_widget: Optional[ActionWidgets] = None
    action_widget_details: Optional[Dict[str, Any]] = None


class StreamingEventData(BaseModel):
    delta: Optional[str] = None
    assistant_message: Optional[str] = None
    questionnaire_id: Optional[int] = None
    action_widget: Optional[ActionWidgets] = None
    action_widget_details: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    is_safe: Optional[bool] = None
    error: Optional[str] = None


class StreamingEvent(BaseModel):
    event: StreamingEventType
    data: StreamingEventData


class WidgetInteractionRequest(BaseModel):
    user_id: str
    session_id: str
    action_widget: ActionWidgets
    action_widget_details: Optional[Dict[str, Any]] = None


# --- Questionnaire schemas ---

class Who5Request(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    user_input: str
    user_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    system_prompt_from_admin: bool = Field(False)
    llm_provider: str = Field("openai")
    llm_model: str = Field("gpt-4o")


class Who5Response(BaseModel):
    assistant_message: str
    is_survey_complete: Optional[bool] = None
    session_id: str
    answers: List[str] = Field(default_factory=list)
    answer_type: Literal["SINGLE", "MULTIPLE"] = "SINGLE"
    final_score: Optional[float] = None
    is_safe: bool


class Who5SummaryRequest(BaseModel):
    user_id: str
    final_score: float
    completed_at: datetime
    dimensions: List[int]


class Who5SummaryResponse(BaseModel):
    user_id: str
    summary: Optional[str] = None
    final_score: Optional[float] = None
    dimensions: Optional[List[Dict[str, Any]]] = None


class OnboardingRequest(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    user_input: str
    user_data: Optional[Dict[str, Any]] = Field(default_factory=dict)
    llm_provider: str = Field("openai")
    llm_model: str = Field("gpt-4o")


class OnboardingResponse(BaseModel):
    assistant_message: str
    answers: List[str] = Field(default_factory=list)
    answer_type: Literal["SINGLE", "MULTIPLE"] = "MULTIPLE"
    question_number: Optional[int] = None
    is_survey_complete: bool
    is_user_suitable: bool = True
    session_id: str
