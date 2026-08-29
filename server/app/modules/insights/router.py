"""AI Insights HTTP router."""

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_guard import get_current_user
from app.modules.auth.schemas import ApiResponse
from app.modules.insights.schemas import (
    ActionItemResponse,
    AllInsightsResponse,
    CreateActionItemRequest,
    DecisionResponse,
    KeyPointResponse,
    UnresolvedIssueResponse,
    UpdateActionItemRequest,
)
from app.modules.insights.service import InsightService

router = APIRouter(prefix="/meetings", tags=["AI Insights"])


@router.get(
    "/{meeting_id}/insights",
    response_model=ApiResponse[AllInsightsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all aggregated insights for meeting (summary, sentiment, actions, decisions, issues)",
)
async def get_all_insights(
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AllInsightsResponse]:
    """Fetches all aggregated insights for the meeting."""
    data = await InsightService.get_all_insights(db, meeting_id, current_user)
    return ApiResponse(success=True, data=data)


@router.get(
    "/{meeting_id}/actions",
    response_model=ApiResponse[list[ActionItemResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get action items for meeting",
)
async def get_actions(
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ActionItemResponse]]:
    """Fetches action items for the meeting."""
    items = await InsightService.get_actions(db, meeting_id, current_user)
    return ApiResponse(success=True, data=items)


@router.post(
    "/{meeting_id}/actions",
    response_model=ApiResponse[ActionItemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new action item manually",
)
async def create_action(
    meeting_id: str,
    payload: CreateActionItemRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ActionItemResponse]:
    """Creates a new action item for a meeting."""
    item = await InsightService.create_action(db, meeting_id, payload, current_user)
    return ApiResponse(success=True, data=item)


@router.patch(
    "/{meeting_id}/actions/{action_id}",
    response_model=ApiResponse[ActionItemResponse],
    status_code=status.HTTP_200_OK,
    summary="Update an action item status, deadline, or description",
)
async def update_action(
    meeting_id: str,
    action_id: str,
    payload: UpdateActionItemRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ActionItemResponse]:
    """Updates an action item."""
    item = await InsightService.update_action(db, meeting_id, action_id, payload, current_user)
    return ApiResponse(success=True, data=item)


@router.delete(
    "/{meeting_id}/actions/{action_id}",
    response_model=ApiResponse[dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Delete an action item",
)
async def delete_action(
    meeting_id: str,
    action_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, Any]]:
    """Deletes an action item."""
    res = await InsightService.delete_action(db, meeting_id, action_id, current_user)
    return ApiResponse(success=True, data=res)


@router.get(
    "/{meeting_id}/decisions",
    response_model=ApiResponse[list[DecisionResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get decisions made in meeting",
)
async def get_decisions(
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[DecisionResponse]]:
    """Fetches decisions for the meeting."""
    items = await InsightService.get_decisions(db, meeting_id, current_user)
    return ApiResponse(success=True, data=items)


@router.get(
    "/{meeting_id}/key-points",
    response_model=ApiResponse[list[KeyPointResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get key discussion points for meeting",
)
async def get_key_points(
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[KeyPointResponse]]:
    """Fetches key points for the meeting."""
    items = await InsightService.get_key_points(db, meeting_id, current_user)
    return ApiResponse(success=True, data=items)


@router.get(
    "/{meeting_id}/issues",
    response_model=ApiResponse[list[UnresolvedIssueResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get unresolved issues for meeting",
)
@router.get(
    "/{meeting_id}/unresolved-issues",
    response_model=ApiResponse[list[UnresolvedIssueResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get unresolved issues for meeting (alias)",
    include_in_schema=False,
)
async def get_unresolved_issues(
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[UnresolvedIssueResponse]]:
    """Fetches unresolved issues for the meeting."""
    items = await InsightService.get_unresolved_issues(db, meeting_id, current_user)
    return ApiResponse(success=True, data=items)
