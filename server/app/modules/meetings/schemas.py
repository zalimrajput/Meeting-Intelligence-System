"""Pydantic schemas for meetings, file uploads, and job status polling."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MeetingResponse(BaseModel):
    """Meeting record schema."""

    id: str = Field(..., description="Meeting UUID")
    owner_id: str = Field(..., description="Owner User UUID")
    title: str = Field(..., description="Meeting title")
    meeting_date: datetime | None = None
    duration_seconds: int | None = None
    status: str = Field(..., description="Meeting status")
    summary_short: str | None = None
    summary_detailed: str | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeetingFileResponse(BaseModel):
    """Uploaded meeting file metadata schema."""

    id: str = Field(..., description="File UUID")
    meeting_id: str = Field(..., description="Meeting UUID")
    file_type: str = Field(..., description="audio or video")
    original_filename: str = Field(..., description="Original uploaded filename")
    storage_path: str = Field(..., description="Object storage path/key")
    format: str = Field(..., description="File extension/format")
    size_bytes: int = Field(..., description="File size in bytes")
    checksum: str = Field(..., description="SHA-256 hex checksum")
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProcessingJobResponse(BaseModel):
    """Background processing job stage schema."""

    id: str = Field(..., description="Job UUID")
    meeting_id: str = Field(..., description="Meeting UUID")
    stage: str = Field(..., description="Processing stage")
    status: str = Field(..., description="Job status: queued, running, completed, failed")
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MeetingUploadResponse(BaseModel):
    """Composite response returned upon successful file upload and job enqueueing."""

    meeting: MeetingResponse
    file: MeetingFileResponse
    job: ProcessingJobResponse

    model_config = ConfigDict(from_attributes=True)


class MeetingStatusResponse(BaseModel):
    """Real-time processing status response for meeting dashboard polling."""

    meeting_id: str = Field(..., description="Meeting UUID")
    status: str = Field(..., description="Overall meeting status")
    failure_reason: str | None = None
    jobs: list[ProcessingJobResponse] = Field(default_factory=list, description="Stage jobs")

    model_config = ConfigDict(from_attributes=True)


class CreateMeetingRequest(BaseModel):
    """Payload to create/initiate meeting record."""

    title: str = Field(..., min_length=1, max_length=255)
    meeting_date: datetime | None = None
