"""Admin HTTP router handling queue status and manual job triggers."""

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_guard import get_current_user
from app.middleware.rate_limiter import limiter
from app.modules.admin.schemas import QueueStatusResponse, QueueTriggerResponse
from app.modules.admin.service import AdminService
from app.modules.auth.schemas import ApiResponse

router = APIRouter(prefix="/admin/queue", tags=["Admin Queue"])


@router.get(
    "/status",
    response_model=ApiResponse[QueueStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="Get background processing queue status and worker health metrics",
)
@limiter.limit("60/minute")
async def get_queue_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> ApiResponse[QueueStatusResponse]:
    """Returns pending, running, completed, and failed job metrics alongside worker heartbeat."""
    status_data = await AdminService.get_queue_status(db)
    return ApiResponse(success=True, data=status_data)


@router.post(
    "/trigger/{meeting_id}",
    response_model=ApiResponse[QueueTriggerResponse],
    status_code=status.HTTP_200_OK,
    summary="Manually re-enqueue a stuck meeting for AI processing",
)
@limiter.limit("20/minute")
async def trigger_meeting_processing(
    request: Request,
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(get_current_user),
) -> ApiResponse[QueueTriggerResponse]:
    """Resets meeting state to 'uploaded' and enqueues job into background queue."""
    result = await AdminService.trigger_meeting_job(db, meeting_id, current_user)
    return ApiResponse(success=True, data=result)
