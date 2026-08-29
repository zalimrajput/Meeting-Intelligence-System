"""Pydantic schemas for Admin Queue monitoring and manual job triggers."""

from pydantic import BaseModel, Field


class QueueJobCounts(BaseModel):
    queued: int = Field(..., description="Count of queued/pending jobs")
    running: int = Field(..., description="Count of currently running jobs")
    completed: int = Field(..., description="Count of completed jobs")
    failed: int = Field(..., description="Count of failed jobs")


class QueueStatusResponse(BaseModel):
    worker_status: str = Field(..., description="Worker status: online, offline, or standalone")
    worker_last_heartbeat: str | None = Field(None, description="Last worker heartbeat ISO timestamp")
    job_counts: QueueJobCounts = Field(..., description="Current breakdown of processing jobs")
    oldest_pending_age_seconds: float = Field(0.0, description="Age in seconds of the oldest pending job")


class QueueTriggerResponse(BaseModel):
    meeting_id: str = Field(..., description="Meeting ID")
    status: str = Field(..., description="Status after manual trigger")
    job_id: str = Field(..., description="Enqueued background job ID")
    message: str = Field(..., description="Result message")
