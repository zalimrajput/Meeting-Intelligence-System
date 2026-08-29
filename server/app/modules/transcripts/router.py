"""Transcripts HTTP router."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_guard import get_current_user
from app.modules.auth.schemas import ApiResponse
from app.modules.transcripts.schemas import TranscriptSegmentResponse
from app.modules.transcripts.service import TranscriptService

router = APIRouter(prefix="/meetings", tags=["Transcripts"])


@router.get(
    "/{meeting_id}/transcript",
    response_model=ApiResponse[list[TranscriptSegmentResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get diarized transcript for a meeting (with optional search keyword filter)",
)
@router.get(
    "/{meeting_id}/transcripts",
    response_model=ApiResponse[list[TranscriptSegmentResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get diarized transcript for a meeting (plural alias)",
    include_in_schema=False,
)
async def get_transcript(
    meeting_id: str,
    search: str | None = Query(None, description="Optional search term to filter transcript segments"),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[TranscriptSegmentResponse]]:
    """Fetches ordered transcript segments for a meeting with optional search query."""
    items = await TranscriptService.get_meeting_transcripts(
        db=db,
        meeting_id=meeting_id,
        current_user=current_user,
        search=search,
    )
    return ApiResponse(success=True, data=items)
