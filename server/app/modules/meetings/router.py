"""Meetings HTTP router handling listing, multipart uploads, status polling, and deletion."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_guard import get_current_user
from app.middleware.rate_limiter import limiter
from app.modules.auth.schemas import ApiResponse
from app.modules.meetings.schemas import (
    MeetingResponse,
    MeetingStatusResponse,
    MeetingUploadResponse,
)
from app.modules.meetings.service import MeetingService

router = APIRouter(prefix="/meetings", tags=["Meetings"])


@router.get(
    "",
    response_model=ApiResponse[list[MeetingResponse]],
    status_code=status.HTTP_200_OK,
    summary="List current user's meetings",
)
@limiter.limit("60/minute")
async def list_meetings(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[MeetingResponse]]:
    """Lists meetings with user data isolation."""
    items, total = await MeetingService.list_user_meetings(db, current_user, page=page, limit=limit)
    return ApiResponse(
        success=True,
        data=items,
        meta={"page": page, "limit": limit, "total": total},
    )


@router.post(
    "",
    response_model=ApiResponse[MeetingUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload meeting recording and initiate processing",
)
@limiter.limit("30/minute")
async def upload_meeting(
    request: Request,
    file: UploadFile = File(..., description="Audio or video file (max 2GB)"),
    title: str | None = Form(None, description="Optional meeting title"),
    meeting_date: datetime | None = Form(None, description="Optional meeting timestamp"),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[MeetingUploadResponse]:
    """
    Accepts multipart/form-data upload, validates magic bytes, streams to storage,
    persists meeting + file + processing job records, and enqueues background processing.
    """
    upload_result = await MeetingService.upload_meeting(
        db=db,
        file=file,
        title=title,
        meeting_date=meeting_date,
        current_user=current_user,
    )
    return ApiResponse(
        success=True,
        data=upload_result,
    )


@router.get(
    "/{meeting_id}",
    response_model=ApiResponse[MeetingResponse],
    status_code=status.HTTP_200_OK,
    summary="Get single meeting details",
)
@limiter.limit("60/minute")
async def get_meeting(
    request: Request,
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[MeetingResponse]:
    """Retrieves single meeting details ensuring ownership."""
    meeting = await MeetingService.get_meeting_by_id(db, meeting_id, current_user)
    return ApiResponse(success=True, data=meeting)


@router.get(
    "/{meeting_id}/status",
    response_model=ApiResponse[MeetingStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="Poll processing status for a meeting",
)
@limiter.limit("60/minute")
async def get_meeting_status(
    request: Request,
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[MeetingStatusResponse]:
    """Returns the current processing_jobs row(s) and overall status for dashboard polling."""
    status_result = await MeetingService.get_meeting_status(db, meeting_id, current_user)
    return ApiResponse(success=True, data=status_result)


@router.delete(
    "/{meeting_id}",
    response_model=ApiResponse[dict[str, str]],
    status_code=status.HTTP_200_OK,
    summary="Delete a meeting, files, and all associated insights",
)
@limiter.limit("20/minute")
async def delete_meeting(
    request: Request,
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, str]]:
    """Hard deletes meeting files from storage and removes all dependent records from PostgreSQL."""
    delete_result = await MeetingService.delete_meeting(db, meeting_id, current_user)
    return ApiResponse(success=True, data=delete_result)


@router.get(
    "/{meeting_id}/media",
    summary="Stream meeting audio/video file for playback with HTTP Range support",
)
@router.get(
    "/{meeting_id}/audio",
    summary="Stream meeting audio/video file (alias)",
    include_in_schema=False,
)
async def stream_meeting_media(
    request: Request,
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Streams the media file for in-browser audio/video playback and waveform sync.
    Handles HTTP Range header for seeking to specific timestamps.
    """
    from fastapi.responses import Response, StreamingResponse
    from pathlib import Path

    file_source, mime_type, file_size, filename = await MeetingService.get_meeting_media(
        db, meeting_id, current_user
    )

    range_header = request.headers.get("range")

    # If full content or no Range header
    if not range_header or "=" not in range_header:
        headers = {
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'inline; filename="{filename}"',
        }
        if isinstance(file_source, Path):
            def file_iter():
                with open(file_source, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        yield chunk
            return StreamingResponse(file_iter(), status_code=200, media_type=mime_type, headers=headers)
        else:
            return Response(content=file_source, status_code=200, media_type=mime_type, headers=headers)

    # Parse Range: bytes=start-end
    try:
        range_val = range_header.split("=")[1].strip()
        parts = range_val.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        start = max(0, start)
        end = min(file_size - 1, end)
        length = (end - start) + 1
    except Exception:
        start = 0
        end = file_size - 1
        length = file_size

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Disposition": f'inline; filename="{filename}"',
    }

    if isinstance(file_source, Path):
        def range_file_iter():
            with open(file_source, "rb") as f:
                f.seek(start)
                bytes_left = length
                while bytes_left > 0:
                    read_size = min(64 * 1024, bytes_left)
                    data = f.read(read_size)
                    if not data:
                        break
                    bytes_left -= len(data)
                    yield data
        return StreamingResponse(range_file_iter(), status_code=206, media_type=mime_type, headers=headers)
    else:
        chunk_bytes = file_source[start : end + 1]
        return Response(content=chunk_bytes, status_code=206, media_type=mime_type, headers=headers)

