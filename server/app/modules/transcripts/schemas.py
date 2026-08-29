"""Pydantic schemas for transcripts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TranscriptSegmentResponse(BaseModel):
    """Segment representing a spoken utterance with timestamps and speaker information."""

    id: str = Field(..., description="Segment UUID")
    meeting_id: str = Field(..., description="Meeting UUID")
    speaker_id: str | None = None
    speaker_label: str | None = None
    segment_index: int
    start_time_seconds: float
    end_time_seconds: float
    text: str
    confidence: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
