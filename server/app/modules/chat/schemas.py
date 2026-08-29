"""Pydantic schemas for Meeting Q&A Chat."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatMessageRequest(BaseModel):
    """Payload to ask a question to AI regarding a meeting."""

    question: str = Field(..., min_length=1, max_length=2000, description="Question text")


class ChatMessageResponse(BaseModel):
    """Saved chat response."""

    id: str = Field(..., description="Message UUID")
    meeting_id: str
    user_id: str
    question: str
    answer: str
    referenced_timestamp_seconds: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
