"""Pydantic schemas for AI Insights (Action items, Decisions, Deadlines, Issues, Key points)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ActionStatusType = Literal["pending", "in_progress", "completed", "overdue"]


class CreateActionItemRequest(BaseModel):
    """Payload for manually creating an action item."""

    task_description: str = Field(..., min_length=1, max_length=1000)
    assigned_to: str | None = None
    deadline_raw_text: str | None = None
    deadline_date: date | None = None
    status: ActionStatusType = "pending"
    timestamp_seconds: float | None = None


class UpdateActionItemRequest(BaseModel):
    """Payload for updating an existing action item."""

    task_description: str | None = None
    assigned_to: str | None = None
    deadline_raw_text: str | None = None
    deadline_date: date | None = None
    status: ActionStatusType | None = None
    timestamp_seconds: float | None = None


class ActionItemResponse(BaseModel):
    """Action item insight."""

    id: str = Field(..., description="Action item UUID")
    meeting_id: str
    task_description: str
    assigned_to: str | None = None
    deadline_raw_text: str | None = None
    deadline_date: date | None = None
    status: str
    timestamp_seconds: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DecisionResponse(BaseModel):
    """Decision insight."""

    id: str = Field(..., description="Decision UUID")
    meeting_id: str
    decision_text: str
    decided_by: str | None = None
    timestamp_seconds: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KeyPointResponse(BaseModel):
    """Key discussion point insight."""

    id: str
    meeting_id: str
    point_text: str
    timestamp_seconds: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UnresolvedIssueResponse(BaseModel):
    """Unresolved issue insight."""

    id: str
    meeting_id: str
    issue_text: str
    timestamp_seconds: float | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AllInsightsResponse(BaseModel):
    """Aggregated insights payload for meeting details view."""

    summary_short: str | None = None
    summary_detailed: str | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    key_points: list[KeyPointResponse] = []
    action_items: list[ActionItemResponse] = []
    decisions: list[DecisionResponse] = []
    unresolved_issues: list[UnresolvedIssueResponse] = []

    model_config = ConfigDict(from_attributes=True)
