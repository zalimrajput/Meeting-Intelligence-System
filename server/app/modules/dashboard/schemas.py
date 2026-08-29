"""Pydantic schemas for Dashboard Intelligence & Global Search."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionStats(BaseModel):
    total: int = 0
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    overdue: int = 0


class SentimentBreakdown(BaseModel):
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    mixed: int = 0


class DashboardStatsResponse(BaseModel):
    """Aggregated stats metrics for the user dashboard."""

    total_meetings: int = 0
    total_duration_seconds: int = 0
    total_duration_minutes: int = 0
    total_hours_formatted: str = "0.0 hrs"
    total_decisions: int = 0
    action_items: ActionStats = Field(default_factory=ActionStats)
    sentiment: SentimentBreakdown = Field(default_factory=SentimentBreakdown)

    model_config = ConfigDict(from_attributes=True)


class UpcomingDeadlineItem(BaseModel):
    """Upcoming deadline item across user's meetings."""

    id: str
    meeting_id: str
    meeting_title: str
    description: str
    raw_text: str | None = None
    resolved_date: date | None = None
    timestamp_seconds: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecentDecisionItem(BaseModel):
    """Recent decision item across user's meetings."""

    id: str
    meeting_id: str
    meeting_title: str
    decision_text: str
    decided_by: str | None = None
    timestamp_seconds: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecentMeetingItem(BaseModel):
    """Enriched recent meeting item for dashboard."""

    id: str
    title: str
    meeting_date: datetime | None = None
    duration_seconds: int = 0
    status: str
    summary_short: str | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    action_items_count: int = 0
    decisions_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GlobalSearchResult(BaseModel):
    """Multi-entity search results across meetings, transcripts, actions, and decisions."""

    query: str
    total_matches: int = 0
    meetings: list[dict[str, Any]] = []
    transcripts: list[dict[str, Any]] = []
    action_items: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
