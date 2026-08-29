"""Export HTTP router for downloading meeting insights and transcripts."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_guard import get_current_user
from app.modules.export.service import ExportService

router = APIRouter(prefix="/meetings", tags=["Meeting Export"])


@router.get(
    "/{meeting_id}/export",
    summary="Export meeting summary, insights, and transcripts in Markdown, JSON, Text, or Email format",
    status_code=status.HTTP_200_OK,
)
async def export_meeting(
    meeting_id: str,
    format: str = Query(
        "markdown",
        description="Export format: 'markdown', 'json', 'email', or 'text'",
        pattern="^(markdown|json|email|text)$",
    ),

    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Exports meeting intelligence report in the requested file format."""
    fmt = format.lower()

    if fmt == "json":
        content, filename = await ExportService.export_json(db, meeting_id, current_user)
        media_type = "application/json"
    elif fmt == "email":
        content, filename = await ExportService.export_email_digest(db, meeting_id, current_user)
        media_type = "text/plain; charset=utf-8"
    elif fmt == "text":
        content, filename = await ExportService.export_text(db, meeting_id, current_user)
        media_type = "text/plain; charset=utf-8"
    else:
        # Default to markdown
        content, filename = await ExportService.export_markdown(db, meeting_id, current_user)
        media_type = "text/markdown; charset=utf-8"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
