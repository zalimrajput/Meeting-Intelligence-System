"""Meeting service handling meeting lifecycle, multipart uploads, status polling, and deletion."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import UploadFile
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import models
from app.core.file_validator import (
    MAX_FILE_SIZE_BYTES,
    detect_mime_type_from_bytes,
)
from app.core.storage import storage_service
from app.middleware.error_handler import AppError
from app.modules.meetings.models import (
    get_meeting_file_model,
    get_meeting_model,
    get_processing_job_model,
)
from app.modules.meetings.schemas import (
    MeetingFileResponse,
    MeetingResponse,
    MeetingStatusResponse,
    MeetingUploadResponse,
    ProcessingJobResponse,
)
from app.services.queue import enqueue_meeting_processing

logger = logging.getLogger(__name__)


class MeetingService:
    """Service handling meeting entity operations with user isolation."""

    @staticmethod
    async def list_user_meetings(
        db: AsyncSession,
        current_user: Any,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[MeetingResponse], int]:
        """Lists meetings belonging to the authenticated user."""
        Meeting = get_meeting_model()
        user_id = current_user.id

        stmt = (
            select(Meeting)
            .where(Meeting.owner_id == user_id)
            .order_by(desc(Meeting.created_at))
            .offset((page - 1) * limit)
            .limit(limit)
        )
        result = await db.execute(stmt)
        meetings = result.scalars().all()

        meeting_items = [
            MeetingResponse(
                id=str(m.id),
                owner_id=str(m.owner_id),
                title=m.title,
                meeting_date=m.meeting_date,
                duration_seconds=m.duration_seconds,
                status=m.status,
                summary_short=m.summary_short,
                summary_detailed=m.summary_detailed,
                sentiment=m.sentiment,
                sentiment_score=(
                    float(m.sentiment_score) if m.sentiment_score is not None else None
                ),
                failure_reason=getattr(m, "failure_reason", None),
                created_at=m.created_at,
                updated_at=m.updated_at,
            )
            for m in meetings
        ]
        return meeting_items, len(meeting_items)

    @staticmethod
    async def get_meeting_by_id(
        db: AsyncSession,
        meeting_id: str,
        current_user: Any,
    ) -> MeetingResponse:
        """Retrieves single meeting details ensuring user ownership."""
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            raise AppError(
                status_code=400, code="INVALID_ID", message="Invalid meeting ID format."
            ) from None

        Meeting = get_meeting_model()
        stmt = select(Meeting).where(Meeting.id == meeting_uuid)
        result = await db.execute(stmt)
        meeting = result.scalars().first()

        if not meeting:
            raise AppError(status_code=404, code="MEETING_NOT_FOUND", message="Meeting not found.")

        if str(meeting.owner_id) != str(current_user.id):
            raise AppError(
                status_code=403,
                code="FORBIDDEN_RESOURCE",
                message="You do not have permission to access this meeting.",
            )

        return MeetingResponse(
            id=str(meeting.id),
            owner_id=str(meeting.owner_id),
            title=meeting.title,
            meeting_date=meeting.meeting_date,
            duration_seconds=meeting.duration_seconds,
            status=meeting.status,
            summary_short=meeting.summary_short,
            summary_detailed=meeting.summary_detailed,
            sentiment=meeting.sentiment,
            sentiment_score=(
                float(meeting.sentiment_score) if meeting.sentiment_score is not None else None
            ),
            failure_reason=getattr(meeting, "failure_reason", None),
            created_at=meeting.created_at,
            updated_at=meeting.updated_at,
        )

    @staticmethod
    async def upload_meeting(
        db: AsyncSession,
        file: UploadFile,
        title: str | None,
        meeting_date: datetime | None,
        current_user: Any,
    ) -> MeetingUploadResponse:
        """
        Validates uploaded audio/video, streams to object storage, creates DB rows atomically,
        and enqueues background processing job.
        """
        filename = file.filename or "uploaded_recording"
        raw_file = file.file

        # Read first 64 bytes for magic bytes validation
        header = raw_file.read(64)
        raw_file.seek(0)

        detected_mime = detect_mime_type_from_bytes(header)
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        if not detected_mime:
            logger.warning("File upload rejected: invalid magic bytes for %s", filename)
            raise AppError(
                status_code=400,
                code="INVALID_FILE_TYPE",
                message="Uploaded file format could not be verified or is not supported.",
            )

        file_type = "video" if detected_mime.startswith("video/") else "audio"

        # Initialize IDs and timestamp
        meeting_uuid = uuid.uuid4()
        file_uuid = uuid.uuid4()
        job_uuid = uuid.uuid4()
        now = datetime.now(UTC)

        effective_title = title.strip() if title and title.strip() else filename
        effective_date = meeting_date or now

        destination_key = f"meetings/{current_user.id}/{meeting_uuid}/{filename}"

        # Stream upload to S3/R2 storage (calculates checksum and size on the fly)
        try:
            storage_path, checksum, size_bytes = await storage_service.upload_file(
                file_obj=raw_file,
                destination_path=destination_key,
                content_type=detected_mime,
            )
        except Exception as e:
            logger.error("Storage upload failed for meeting %s: %s", str(meeting_uuid), str(e))
            raise AppError(
                status_code=500,
                code="STORAGE_ERROR",
                message="Failed to upload file to storage.",
            ) from e

        # Validate file size limit
        if size_bytes > MAX_FILE_SIZE_BYTES:
            await storage_service.delete_file(destination_key)
            raise AppError(
                status_code=400,
                code="FILE_TOO_LARGE",
                message=f"File size ({size_bytes} bytes) exceeds maximum allowable limit of 2GB.",
            )

        Meeting = get_meeting_model()
        MeetingFile = get_meeting_file_model()
        ProcessingJob = get_processing_job_model()

        # 1. Create Meeting record
        new_meeting = Meeting(
            id=meeting_uuid,
            owner_id=current_user.id,
            title=effective_title,
            meeting_date=effective_date,
            status="uploaded",
            created_at=now,
            updated_at=now,
        )
        db.add(new_meeting)

        # 2. Create MeetingFile record
        new_file = MeetingFile(
            id=file_uuid,
            meeting_id=meeting_uuid,
            file_type=file_type,
            original_filename=filename,
            storage_path=storage_path,
            format=ext,
            size_bytes=size_bytes,
            checksum=checksum,
            uploaded_at=now,
        )
        db.add(new_file)

        # 3. Create ProcessingJob record
        new_job = ProcessingJob(
            id=job_uuid,
            meeting_id=meeting_uuid,
            stage="transcription",
            status="queued",
            created_at=now,
        )
        db.add(new_job)

        # Commit DB records atomically
        await db.commit()
        await db.refresh(new_meeting)
        await db.refresh(new_file)
        await db.refresh(new_job)

        # 4. Enqueue processing job via arq
        await enqueue_meeting_processing(str(meeting_uuid))

        meeting_resp = MeetingResponse(
            id=str(new_meeting.id),
            owner_id=str(new_meeting.owner_id),
            title=new_meeting.title,
            meeting_date=new_meeting.meeting_date,
            duration_seconds=new_meeting.duration_seconds,
            status=new_meeting.status,
            summary_short=new_meeting.summary_short,
            summary_detailed=new_meeting.summary_detailed,
            sentiment=new_meeting.sentiment,
            sentiment_score=None,
            failure_reason=new_meeting.failure_reason,
            created_at=new_meeting.created_at,
            updated_at=new_meeting.updated_at,
        )

        file_resp = MeetingFileResponse(
            id=str(new_file.id),
            meeting_id=str(new_file.meeting_id),
            file_type=new_file.file_type,
            original_filename=new_file.original_filename,
            storage_path=new_file.storage_path,
            format=new_file.format,
            size_bytes=new_file.size_bytes,
            checksum=new_file.checksum,
            uploaded_at=new_file.uploaded_at,
        )

        job_resp = ProcessingJobResponse(
            id=str(new_job.id),
            meeting_id=str(new_job.meeting_id),
            stage=new_job.stage,
            status=new_job.status,
            error_message=new_job.error_message,
            started_at=new_job.started_at,
            completed_at=new_job.completed_at,
            created_at=new_job.created_at,
        )

        logger.info(
            "Successfully created meeting=%s file=%s job=%s for owner=%s",
            str(meeting_uuid),
            str(file_uuid),
            str(job_uuid),
            str(current_user.id),
        )

        return MeetingUploadResponse(
            meeting=meeting_resp,
            file=file_resp,
            job=job_resp,
        )

    @staticmethod
    async def get_meeting_status(
        db: AsyncSession,
        meeting_id: str,
        current_user: Any,
    ) -> MeetingStatusResponse:
        """Returns processing status and all processing_jobs for a meeting."""
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            raise AppError(
                status_code=400, code="INVALID_ID", message="Invalid meeting ID format."
            ) from None

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
                message="You do not have permission to view status for this meeting.",
            )

        ProcessingJob = get_processing_job_model()
        stmt_j = (
            select(ProcessingJob)
            .where(ProcessingJob.meeting_id == meeting_uuid)
            .order_by(ProcessingJob.created_at.asc())
        )
        res_j = await db.execute(stmt_j)
        jobs = res_j.scalars().all()

        job_responses = [
            ProcessingJobResponse(
                id=str(j.id),
                meeting_id=str(j.meeting_id),
                stage=j.stage,
                status=j.status,
                error_message=j.error_message,
                started_at=j.started_at,
                completed_at=j.completed_at,
                created_at=j.created_at,
            )
            for j in jobs
        ]

        return MeetingStatusResponse(
            meeting_id=str(meeting.id),
            status=meeting.status,
            failure_reason=getattr(meeting, "failure_reason", None),
            jobs=job_responses,
        )

    @staticmethod
    async def delete_meeting(
        db: AsyncSession,
        meeting_id: str,
        current_user: Any,
    ) -> dict[str, str]:
        """
        Deletes meeting files from object storage and hard-deletes all associated database rows.
        """
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            raise AppError(
                status_code=400, code="INVALID_ID", message="Invalid meeting ID format."
            ) from None

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
                message="You do not have permission to delete this meeting.",
            )

        # 1. Fetch meeting_files and delete from storage
        MeetingFile = get_meeting_file_model()
        stmt_f = select(MeetingFile).where(MeetingFile.meeting_id == meeting_uuid)
        res_f = await db.execute(stmt_f)
        files = res_f.scalars().all()

        for f in files:
            if f.storage_path:
                await storage_service.delete_file(f.storage_path)

        # 2. Hard delete all related records in FK dependency order
        models_to_clean = [
            models.Deadline,
            models.ActionItem,
            models.Decision,
            models.UnresolvedIssue,
            models.FollowUpItem,
            models.KeyPoint,
            models.AIConversation,
            models.TranscriptSegment,
            models.Speaker,
            models.Participant,
            models.ProcessingJob,
            models.MeetingFile,
            models.Meeting,
        ]

        for model_cls in models_to_clean:
            if model_cls is not None:
                if hasattr(model_cls, "meeting_id"):
                    await db.execute(delete(model_cls).where(model_cls.meeting_id == meeting_uuid))
                elif hasattr(model_cls, "id"):
                    await db.execute(delete(model_cls).where(model_cls.id == meeting_uuid))

        await db.commit()
        logger.info("Hard deleted meeting and all child rows for meeting_id=%s", meeting_id)

        return {"message": "Meeting and associated resources deleted successfully."}

    @staticmethod
    async def get_meeting_media(
        db: AsyncSession,
        meeting_id: str,
        current_user: Any,
    ) -> tuple[Any, str, int, str]:
        """
        Retrieves the media file record, file path / bytes, total size, and mime type for playback streaming.
        Returns: (file_path_or_bytes, mime_type, file_size, filename)
        """
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            raise AppError(
                status_code=400, code="INVALID_ID", message="Invalid meeting ID format."
            ) from None

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
                message="You do not have permission to access media for this meeting.",
            )

        MeetingFile = get_meeting_file_model()
        stmt_f = select(MeetingFile).where(MeetingFile.meeting_id == meeting_uuid)
        res_f = await db.execute(stmt_f)
        meeting_file = res_f.scalars().first()

        if not meeting_file or not meeting_file.storage_path:
            raise AppError(
                status_code=404,
                code="MEDIA_NOT_FOUND",
                message="No media file is attached to this meeting.",
            )

        import mimetypes

        storage_path = meeting_file.storage_path
        filename = meeting_file.original_filename or f"meeting_{meeting_id}.mp3"
        guessed_type, _ = mimetypes.guess_type(filename)
        mime_type = guessed_type or ("video/mp4" if getattr(meeting_file, "file_type", "") == "video" else "audio/mpeg")
        local_p = storage_service.get_local_path(storage_path)


        if local_p and local_p.exists():
            file_size = local_p.stat().st_size
            return local_p, mime_type, file_size, filename
        else:
            file_bytes = await storage_service.get_file_bytes(storage_path)
            file_size = len(file_bytes)
            return file_bytes, mime_type, file_size, filename

