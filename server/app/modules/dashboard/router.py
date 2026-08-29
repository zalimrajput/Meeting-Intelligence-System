"""Dashboard Intelligence & Global Search HTTP router."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_guard import get_current_user
from app.modules.auth.schemas import ApiResponse
from app.modules.dashboard.schemas import (
    DashboardStatsResponse,
    GlobalSearchResult,
    RecentDecisionItem,
    RecentMeetingItem,
    UpcomingDeadlineItem,
)
from app.modules.dashboard.service import DashboardService

router = APIRouter(tags=["Dashboard & Search"])


@router.get(
    "/dashboard/stats",
    response_model=ApiResponse[DashboardStatsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get aggregated meeting intelligence statistics for dashboard",
)
async def get_dashboard_stats(
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[DashboardStatsResponse]:
    """Retrieves total meetings, duration, action item status counts, and sentiment breakdown."""
    stats = await DashboardService.get_stats(db, current_user)
    return ApiResponse(success=True, data=stats)


@router.get(
    "/dashboard/deadlines",
    response_model=ApiResponse[list[UpcomingDeadlineItem]],
    status_code=status.HTTP_200_OK,
    summary="Get upcoming deadlines widget feed across all meetings",
)
async def get_upcoming_deadlines(
    limit: int = Query(10, ge=1, le=50, description="Max deadlines to return"),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[UpcomingDeadlineItem]]:
    """Retrieves upcoming deadlines ordered chronologically."""
    items = await DashboardService.get_upcoming_deadlines(db, current_user, limit=limit)
    return ApiResponse(success=True, data=items)


@router.get(
    "/dashboard/decisions",
    response_model=ApiResponse[list[RecentDecisionItem]],
    status_code=status.HTTP_200_OK,
    summary="Get recent decisions widget feed across all meetings",
)
async def get_recent_decisions(
    limit: int = Query(10, ge=1, le=50, description="Max decisions to return"),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[RecentDecisionItem]]:
    """Retrieves recent decisions ordered by creation date."""
    items = await DashboardService.get_recent_decisions(db, current_user, limit=limit)
    return ApiResponse(success=True, data=items)


@router.get(
    "/dashboard/recent-meetings",
    response_model=ApiResponse[list[RecentMeetingItem]],
    status_code=status.HTTP_200_OK,
    summary="Get recent meetings list with action item and decision counts",
)
async def get_recent_meetings(
    limit: int = Query(10, ge=1, le=50, description="Max meetings to return"),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[RecentMeetingItem]]:
    """Retrieves recent meetings enriched with counts for dashboard."""
    items = await DashboardService.get_recent_meetings(db, current_user, limit=limit)
    return ApiResponse(success=True, data=items)


@router.get(
    "/search",
    response_model=ApiResponse[GlobalSearchResult],
    status_code=status.HTTP_200_OK,
    summary="Global search across all meetings, transcripts, action items, and decisions",
)
@router.get(
    "/dashboard/search",
    response_model=ApiResponse[GlobalSearchResult],
    status_code=status.HTTP_200_OK,
    summary="Global search (alias)",
    include_in_schema=False,
)
async def global_search(
    q: str = Query(..., min_length=1, max_length=200, description="Search term or phrase"),
    limit: int = Query(20, ge=1, le=100, description="Max results per category"),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[GlobalSearchResult]:
    """Searches meetings, transcript segments, actions, and decisions for the authenticated user."""
    results = await DashboardService.global_search(
        db=db,
        query=q,
        current_user=current_user,
        limit=limit,
    )
    return ApiResponse(success=True, data=results)
