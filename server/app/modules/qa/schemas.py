"""Pydantic schemas for Meeting Q&A Chat."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AskQuestionRequest(BaseModel):
    """Payload for asking a question about a meeting."""

    question: str = Field(..., min_length=1, max_length=2000, description="Question text")


class ChatMessageResponse(BaseModel):
    """Chat message representation."""

    id: str = Field(..., description="Conversation UUID")
    meeting_id: str
    user_id: str
    question: str
    answer: str
    referenced_timestamp_seconds: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatHistoryResponse(BaseModel):
    """List of chat messages for a meeting."""

    messages: list[ChatMessageResponse]
