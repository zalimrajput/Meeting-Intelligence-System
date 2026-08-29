"""Admin service handling queue status monitoring and manual job re-triggering."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import models
from app.modules.admin.schemas import QueueJobCounts, QueueStatusResponse, QueueTriggerResponse
from app.services.queue import enqueue_meeting_processing, get_redis_pool

logger = logging.getLogger(__name__)

HEARTBEAT_KEY = "meetingmind:worker:heartbeat"


class AdminService:
    """Service providing queue monitoring metrics and manual job recovery operations."""

    @staticmethod
    async def get_queue_status(db: AsyncSession) -> QueueStatusResponse:
        """Computes pending, running, completed, and failed job counts, and worker health."""
        ProcessingJob = models.ProcessingJob

        # Aggregate counts by status
        stmt = (
            select(ProcessingJob.status, func.count(ProcessingJob.id))
            .group_by(ProcessingJob.status)
        )
        res = await db.execute(stmt)
        rows = res.all()
        counts_map = {status: count for status, count in rows}

        queued_count = counts_map.get("queued", 0)
        running_count = counts_map.get("running", 0)
        completed_count = counts_map.get("completed", 0)
        failed_count = counts_map.get("failed", 0)

        # Oldest queued job age
        oldest_pending_stmt = (
            select(ProcessingJob.created_at)
            .where(ProcessingJob.status == "queued")
            .order_by(ProcessingJob.created_at.asc())
            .limit(1)
        )
        oldest_res = await db.execute(oldest_pending_stmt)
        oldest_created_at = oldest_res.scalars().first()

        now = datetime.now(UTC)
        oldest_age_sec = 0.0
        if oldest_created_at:
            if oldest_created_at.tzinfo is None:
                oldest_created_at = oldest_created_at.replace(tzinfo=UTC)
            oldest_age_sec = max(0.0, (now - oldest_created_at).total_seconds())

        # Check Redis worker heartbeat
        worker_status = "offline"
        last_heartbeat_iso = None

        try:
            pool = await get_redis_pool()
            if pool:
                hb_val = await pool.get(HEARTBEAT_KEY)
                if hb_val:
                    last_heartbeat_iso = hb_val.decode("utf-8") if isinstance(hb_val, bytes) else str(hb_val)
                    hb_dt = datetime.fromisoformat(last_heartbeat_iso)
                    if hb_dt.tzinfo is None:
                        hb_dt = hb_dt.replace(tzinfo=UTC)
                    if (now - hb_dt).total_seconds() < 30:
                        worker_status = "online"
                    else:
                        worker_status = "stale"
            else:
                worker_status = "standalone_async"
        except Exception as e:
            logger.debug("Could not query Redis heartbeat: %s", e)
            worker_status = "unknown"

        return QueueStatusResponse(
            worker_status=worker_status,
            worker_last_heartbeat=last_heartbeat_iso,
            job_counts=QueueJobCounts(
                queued=queued_count,
                running=running_count,
                completed=completed_count,
                failed=failed_count,
            ),
            oldest_pending_age_seconds=round(oldest_age_sec, 2),
        )

    @staticmethod
    async def trigger_meeting_job(
        db: AsyncSession,
        meeting_id: str,
        current_user: Any,
    ) -> QueueTriggerResponse:
        """Manually resets a meeting's state to 'uploaded' and re-enqueues processing."""
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            from app.middleware.error_handler import CustomAppException

            raise CustomAppException(
                status_code=400,
                error_code="INVALID_UUID",
                message=f"Invalid meeting UUID: {meeting_id}",
            )

        Meeting = models.Meeting
        ProcessingJob = models.ProcessingJob

        stmt = select(Meeting).where(Meeting.id == meeting_uuid)
        res = await db.execute(stmt)
        meeting = res.scalars().first()

        if not meeting:
            from app.middleware.error_handler import CustomAppException

            raise CustomAppException(
                status_code=404,
                error_code="MEETING_NOT_FOUND",
                message=f"Meeting not found: {meeting_id}",
            )

        now = datetime.now(UTC)
        meeting.status = "uploaded"
        meeting.failure_reason = None
        meeting.updated_at = now

        # Reset or create transcription job
        job_stmt = select(ProcessingJob).where(
            ProcessingJob.meeting_id == meeting_uuid,
            ProcessingJob.stage == "transcription",
        )
        job_res = await db.execute(job_stmt)
        job = job_res.scalars().first()

        if job:
            job.status = "queued"
            job.started_at = None
            job.completed_at = None
            job.error_message = None
        else:
            job = ProcessingJob(
                id=uuid.uuid4(),
                meeting_id=meeting_uuid,
                stage="transcription",
                status="queued",
                created_at=now,
            )
            db.add(job)

        await db.commit()

        # Enqueue in background queue
        job_id = await enqueue_meeting_processing(str(meeting_uuid))

        logger.info(
            "Admin manually triggered re-processing for meeting %s (job_id=%s)",
            meeting_id,
            job_id,
        )

        return QueueTriggerResponse(
            meeting_id=meeting_id,
            status="uploaded",
            job_id=job_id,
            message="Meeting re-enqueued successfully for processing.",
        )
