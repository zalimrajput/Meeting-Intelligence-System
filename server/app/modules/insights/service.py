"""AI Insights service for retrieving and managing structured meeting takeaways with ownership checks."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.error_handler import AppError
from app.modules.insights.models import (
    get_action_item_model,
    get_decision_model,
    get_key_point_model,
    get_unresolved_issue_model,
)
from app.modules.insights.schemas import (
    ActionItemResponse,
    AllInsightsResponse,
    CreateActionItemRequest,
    DecisionResponse,
    KeyPointResponse,
    UnresolvedIssueResponse,
    UpdateActionItemRequest,
)
from app.modules.meetings.models import get_meeting_model


class InsightService:
    """Service handling meeting insights retrieval and mutations."""

    @staticmethod
    async def _verify_meeting_access(
        db: AsyncSession, meeting_id: str, current_user: Any
    ) -> tuple[uuid.UUID, Any]:
        """Helper to verify meeting existence and user ownership. Returns (meeting_uuid, meeting_model)."""
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            raise AppError(
                status_code=400,
                code="INVALID_ID",
                message="Invalid meeting ID.",
            ) from None

        Meeting = get_meeting_model()
        stmt = select(Meeting).where(Meeting.id == meeting_uuid)
        res = await db.execute(stmt)
        meeting = res.scalars().first()

        if not meeting:
            raise AppError(status_code=404, code="MEETING_NOT_FOUND", message="Meeting not found.")

        if str(meeting.owner_id) != str(current_user.id):
            raise AppError(
                status_code=403,
                code="FORBIDDEN_RESOURCE",
                message="You do not have permission to view insights for this meeting.",
            )

        return meeting_uuid, meeting

    @staticmethod
    async def get_actions(
        db: AsyncSession, meeting_id: str, current_user: Any
    ) -> list[ActionItemResponse]:
        """Gets action items for a meeting."""
        meeting_uuid, _ = await InsightService._verify_meeting_access(db, meeting_id, current_user)
        ActionItem = get_action_item_model()
        stmt = (
            select(ActionItem)
            .where(ActionItem.meeting_id == meeting_uuid)
            .order_by(ActionItem.created_at.asc())
        )
        res = await db.execute(stmt)
        items = res.scalars().all()
        return [
            ActionItemResponse(
                id=str(item.id),
                meeting_id=str(item.meeting_id),
                task_description=item.task_description,
                assigned_to=str(item.assigned_to) if item.assigned_to else None,
                deadline_raw_text=item.deadline_raw_text,
                deadline_date=item.deadline_date,
                status=item.status,
                timestamp_seconds=(
                    float(item.timestamp_seconds) if item.timestamp_seconds is not None else None
                ),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]

    @staticmethod
    async def create_action(
        db: AsyncSession,
        meeting_id: str,
        payload: CreateActionItemRequest,
        current_user: Any,
    ) -> ActionItemResponse:
        """Manually creates a new action item for a meeting."""
        meeting_uuid, _ = await InsightService._verify_meeting_access(db, meeting_id, current_user)
        ActionItem = get_action_item_model()
        now = datetime.now(UTC)

        new_action = ActionItem(
            id=uuid.uuid4(),
            meeting_id=meeting_uuid,
            task_description=payload.task_description,
            assigned_to=None,
            deadline_raw_text=payload.deadline_raw_text,
            deadline_date=payload.deadline_date,
            status=payload.status,
            timestamp_seconds=payload.timestamp_seconds,
            created_at=now,
            updated_at=now,
        )
        db.add(new_action)
        await db.commit()
        await db.refresh(new_action)

        return ActionItemResponse(
            id=str(new_action.id),
            meeting_id=str(new_action.meeting_id),
            task_description=new_action.task_description,
            assigned_to=str(new_action.assigned_to) if new_action.assigned_to else None,
            deadline_raw_text=new_action.deadline_raw_text,
            deadline_date=new_action.deadline_date,
            status=new_action.status,
            timestamp_seconds=(
                float(new_action.timestamp_seconds)
                if new_action.timestamp_seconds is not None
                else None
            ),
            created_at=new_action.created_at,
            updated_at=new_action.updated_at,
        )

    @staticmethod
    async def update_action(
        db: AsyncSession,
        meeting_id: str,
        action_id: str,
        payload: UpdateActionItemRequest,
        current_user: Any,
    ) -> ActionItemResponse:
        """Updates status, deadline, or description of an existing action item."""
        meeting_uuid, _ = await InsightService._verify_meeting_access(db, meeting_id, current_user)
        try:
            action_uuid = uuid.UUID(action_id)
        except (ValueError, TypeError):
            raise AppError(status_code=400, code="INVALID_ID", message="Invalid action item ID.") from None

        ActionItem = get_action_item_model()
        stmt = select(ActionItem).where(
            ActionItem.id == action_uuid, ActionItem.meeting_id == meeting_uuid
        )
        res = await db.execute(stmt)
        item = res.scalars().first()

        if not item:
            raise AppError(status_code=404, code="ACTION_NOT_FOUND", message="Action item not found.")

        now = datetime.now(UTC)
        if payload.task_description is not None:
            item.task_description = payload.task_description
        if payload.deadline_raw_text is not None:
            item.deadline_raw_text = payload.deadline_raw_text
        if payload.deadline_date is not None:
            item.deadline_date = payload.deadline_date
        if payload.status is not None:
            item.status = payload.status
        if payload.timestamp_seconds is not None:
            item.timestamp_seconds = payload.timestamp_seconds

        item.updated_at = now
        await db.commit()
        await db.refresh(item)

        return ActionItemResponse(
            id=str(item.id),
            meeting_id=str(item.meeting_id),
            task_description=item.task_description,
            assigned_to=str(item.assigned_to) if item.assigned_to else None,
            deadline_raw_text=item.deadline_raw_text,
            deadline_date=item.deadline_date,
            status=item.status,
            timestamp_seconds=(
                float(item.timestamp_seconds) if item.timestamp_seconds is not None else None
            ),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    async def delete_action(
        db: AsyncSession,
        meeting_id: str,
        action_id: str,
        current_user: Any,
    ) -> dict[str, Any]:
        """Deletes an action item with ownership checks."""
        meeting_uuid, _ = await InsightService._verify_meeting_access(db, meeting_id, current_user)
        try:
            action_uuid = uuid.UUID(action_id)
        except (ValueError, TypeError):
            raise AppError(status_code=400, code="INVALID_ID", message="Invalid action item ID.") from None

        ActionItem = get_action_item_model()
        stmt = select(ActionItem).where(
            ActionItem.id == action_uuid, ActionItem.meeting_id == meeting_uuid
        )
        res = await db.execute(stmt)
        item = res.scalars().first()

        if not item:
            raise AppError(status_code=404, code="ACTION_NOT_FOUND", message="Action item not found.")

        await db.execute(delete(ActionItem).where(ActionItem.id == action_uuid))
        await db.commit()

        return {"deleted": True, "action_id": action_id}

    @staticmethod
    async def get_decisions(
        db: AsyncSession, meeting_id: str, current_user: Any
    ) -> list[DecisionResponse]:
        """Gets decisions for a meeting."""
        meeting_uuid, _ = await InsightService._verify_meeting_access(db, meeting_id, current_user)
        Decision = get_decision_model()
        stmt = (
            select(Decision)
            .where(Decision.meeting_id == meeting_uuid)
            .order_by(Decision.created_at.asc())
        )
        res = await db.execute(stmt)
        items = res.scalars().all()
        return [
            DecisionResponse(
                id=str(item.id),
                meeting_id=str(item.meeting_id),
                decision_text=item.decision_text,
                decided_by=str(item.decided_by) if item.decided_by else None,
                timestamp_seconds=(
                    float(item.timestamp_seconds) if item.timestamp_seconds is not None else None
                ),
                created_at=item.created_at,
            )
            for item in items
        ]

    @staticmethod
    async def get_key_points(
        db: AsyncSession, meeting_id: str, current_user: Any
    ) -> list[KeyPointResponse]:
        """Gets key points for a meeting."""
        meeting_uuid, _ = await InsightService._verify_meeting_access(db, meeting_id, current_user)
        KeyPoint = get_key_point_model()
        stmt = (
            select(KeyPoint)
            .where(KeyPoint.meeting_id == meeting_uuid)
            .order_by(KeyPoint.created_at.asc())
        )
        res = await db.execute(stmt)
        items = res.scalars().all()
        return [
            KeyPointResponse(
                id=str(item.id),
                meeting_id=str(item.meeting_id),
                point_text=item.point_text,
                timestamp_seconds=(
                    float(item.timestamp_seconds) if item.timestamp_seconds is not None else None
                ),
                created_at=item.created_at,
            )
            for item in items
        ]

    @staticmethod
    async def get_unresolved_issues(
        db: AsyncSession, meeting_id: str, current_user: Any
    ) -> list[UnresolvedIssueResponse]:
        """Gets unresolved issues for a meeting."""
        meeting_uuid, _ = await InsightService._verify_meeting_access(db, meeting_id, current_user)
        UnresolvedIssue = get_unresolved_issue_model()
        stmt = (
            select(UnresolvedIssue)
            .where(UnresolvedIssue.meeting_id == meeting_uuid)
            .order_by(UnresolvedIssue.created_at.asc())
        )
        res = await db.execute(stmt)
        items = res.scalars().all()
        return [
            UnresolvedIssueResponse(
                id=str(item.id),
                meeting_id=str(item.meeting_id),
                issue_text=item.issue_text,
                timestamp_seconds=(
                    float(item.timestamp_seconds) if item.timestamp_seconds is not None else None
                ),
                created_at=item.created_at,
            )
            for item in items
        ]

    @staticmethod
    async def get_all_insights(
        db: AsyncSession, meeting_id: str, current_user: Any
    ) -> AllInsightsResponse:
        """Retrieves aggregated summary, sentiment, key points, actions, decisions, and issues."""
        _, meeting = await InsightService._verify_meeting_access(db, meeting_id, current_user)
        actions = await InsightService.get_actions(db, meeting_id, current_user)
        decisions = await InsightService.get_decisions(db, meeting_id, current_user)
        key_points = await InsightService.get_key_points(db, meeting_id, current_user)
        issues = await InsightService.get_unresolved_issues(db, meeting_id, current_user)

        return AllInsightsResponse(
            summary_short=meeting.summary_short,
            summary_detailed=meeting.summary_detailed,
            sentiment=meeting.sentiment,
            sentiment_score=(
                float(meeting.sentiment_score) if meeting.sentiment_score is not None else None
            ),
            key_points=key_points,
            action_items=actions,
            decisions=decisions,
            unresolved_issues=issues,
        )
