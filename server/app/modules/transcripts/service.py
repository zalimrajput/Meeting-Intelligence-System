"""Transcript service for retrieving and querying diarized transcript segments."""

import uuid
from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.error_handler import AppError
from app.modules.meetings.models import get_meeting_model
from app.modules.transcripts.models import get_speaker_model, get_transcript_segment_model
from app.modules.transcripts.schemas import TranscriptSegmentResponse


class TranscriptService:
    """Service handling transcript data retrieval with meeting ownership checks."""

    @staticmethod
    async def get_meeting_transcripts(
        db: AsyncSession,
        meeting_id: str,
        current_user: Any,
        search: str | None = None,
    ) -> list[TranscriptSegmentResponse]:
        """Retrieves all ordered transcript segments for a meeting owned by user, with optional search filtering."""
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            raise AppError(
                status_code=400,
                code="INVALID_ID",
                message="Invalid meeting ID.",
            ) from None

        # Check meeting exists and belongs to current user
        Meeting = get_meeting_model()
        stmt_m = select(Meeting).where(Meeting.id == meeting_uuid)
        res_m = await db.execute(stmt_m)
        meeting = res_m.scalars().first()

        if not meeting:
            raise AppError(status_code=404, code="MEETING_NOT_FOUND", message="Meeting not found.")

        if str(meeting.owner_id) != str(current_user.id):
            raise AppError(
                status_code=403,
                code="FORBIDDEN_RESOURCE",
                message="You do not have access to this meeting's transcripts.",
            )

        TranscriptSegment = get_transcript_segment_model()
        Speaker = get_speaker_model()

        stmt_t = (
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_uuid)
            .order_by(asc(TranscriptSegment.segment_index))
        )
        if search and search.strip():
            stmt_t = stmt_t.where(TranscriptSegment.text.ilike(f"%{search.strip()}%"))

        res_t = await db.execute(stmt_t)
        segments = res_t.scalars().all()

        speaker_map: dict[str, str] = {}
        if Speaker is not None:
            stmt_s = select(Speaker).where(Speaker.meeting_id == meeting_uuid)
            res_s = await db.execute(stmt_s)
            speakers = res_s.scalars().all()
            for s in speakers:
                speaker_map[str(s.id)] = s.speaker_label

        return [
            TranscriptSegmentResponse(
                id=str(seg.id),
                meeting_id=str(seg.meeting_id),
                speaker_id=str(seg.speaker_id) if seg.speaker_id else None,
                speaker_label=(
                    speaker_map.get(str(seg.speaker_id), "Speaker") if seg.speaker_id else None
                ),
                segment_index=seg.segment_index,
                start_time_seconds=float(seg.start_time_seconds),
                end_time_seconds=float(seg.end_time_seconds),
                text=seg.text,
                confidence=float(seg.confidence) if seg.confidence is not None else None,
                created_at=seg.created_at,
            )
            for seg in segments
        ]
