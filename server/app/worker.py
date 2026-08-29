"""Background job worker using arq (Redis-backed async job queue).

Defines worker settings and task handlers for meeting processing lifecycle.
Executes Stage 1 (DeepGram Transcription & Speaker Diarization) and Stage 2 (Gemini Insights Extraction).
"""

import logging
import tempfile
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text

from app.core.config import settings
from app.core.database import async_session_maker, init_db, models
from app.core.storage import storage_service
from app.services.deepgram_service import deepgram_service
from app.services.gemini_service import gemini_service
from app.services.media_preprocessor import extract_audio_from_video, is_ffmpeg_available

try:
    from arq.connections import RedisSettings
except ImportError:
    RedisSettings = None

logger = logging.getLogger("meetingmind.worker")


def format_seconds_to_timestamp(seconds: float) -> str:
    """Formats float seconds into MM:SS timestamp string."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


async def startup(ctx: dict[str, Any]) -> None:
    """Worker startup hook: initializes database reflection."""
    logger.info("Starting up MeetingMind background worker...")
    await init_db()
    ctx["db_ready"] = True
    logger.info("Background worker initialized successfully.")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Worker shutdown hook."""
    logger.info("Shutting down MeetingMind background worker...")


async def process_meeting(ctx: dict[str, Any] | None, meeting_id: str) -> dict[str, Any]:
    """
    Background job that orchestrates the full AI pipeline for a meeting.

    Stage 1: DeepGram Audio Transcription & Speaker Diarization
    Stage 2: Google Gemini Intelligence Extraction (Summary, Actions, Decisions, Issues, Sentiment)
    """
    logger.info("Processing meeting job started: meeting_id=%s", meeting_id)

    try:
        meeting_uuid = uuid.UUID(meeting_id)
    except (ValueError, TypeError):
        logger.error("Invalid meeting UUID passed to worker: %s", meeting_id)
        return {"status": "error", "message": "Invalid meeting ID format"}

    temp_files_to_cleanup: list[Path] = []

    try:
        # Initialize DB reflection if not ready
        if not models.Meeting or not models.ProcessingJob or not models.TranscriptSegment:
            await init_db()

        Meeting = models.Meeting
        MeetingFile = models.MeetingFile
        ProcessingJob = models.ProcessingJob
        Speaker = models.Speaker
        TranscriptSegment = models.TranscriptSegment
        ActionItem = models.ActionItem
        Decision = models.Decision
        UnresolvedIssue = models.UnresolvedIssue
        FollowUpItem = models.FollowUpItem
        KeyPoint = models.KeyPoint
        Deadline = models.Deadline

        # =========================================================================
        # Stage 1: DeepGram Transcription & Diarization
        # =========================================================================
        async with async_session_maker() as db:
            stmt_m = select(Meeting).where(Meeting.id == meeting_uuid)
            res_m = await db.execute(stmt_m)
            meeting = res_m.scalars().first()

            if not meeting:
                logger.error("Meeting not found for processing: meeting_id=%s", meeting_id)
                return {"status": "error", "message": "Meeting not found"}

            stmt_f = select(MeetingFile).where(MeetingFile.meeting_id == meeting_uuid)
            res_f = await db.execute(stmt_f)
            meeting_file = res_f.scalars().first()

            if not meeting_file:
                logger.error("No file associated with meeting: meeting_id=%s", meeting_id)
                raise FileNotFoundError(f"Meeting file record missing for meeting {meeting_id}")

            now = datetime.now(UTC)

            # Update meeting status to transcribing
            meeting.status = "transcribing"
            meeting.updated_at = now

            # Update or create processing job for transcription stage
            stmt_j = select(ProcessingJob).where(
                ProcessingJob.meeting_id == meeting_uuid,
                ProcessingJob.stage == "transcription",
            )
            res_j = await db.execute(stmt_j)
            job = res_j.scalars().first()

            if job:
                job.status = "running"
                job.started_at = now
                job.completed_at = None
                job.error_message = None
            else:
                job = ProcessingJob(
                    id=uuid.uuid4(),
                    meeting_id=meeting_uuid,
                    stage="transcription",
                    status="running",
                    started_at=now,
                    completed_at=None,
                    created_at=now,
                )
                db.add(job)

            await db.commit()

        # Retrieve media file from storage
        storage_path = meeting_file.storage_path
        file_type = meeting_file.file_type
        local_path = storage_service.get_local_path(storage_path)

        if local_path and local_path.exists():
            input_media_path = local_path
        else:
            file_bytes = await storage_service.get_file_bytes(storage_path)
            temp_in = (
                Path(tempfile.gettempdir())
                / f"mm_in_{meeting_id}_{meeting_file.original_filename}"
            )
            temp_in.write_bytes(file_bytes)
            input_media_path = temp_in
            temp_files_to_cleanup.append(temp_in)

        # Handle video audio extraction if video input
        audio_for_transcription_path = input_media_path
        is_video = file_type == "video" or input_media_path.suffix.lower() in [
            ".mp4",
            ".mov",
            ".avi",
            ".mkv",
            ".webm",
            ".flv",
            ".wmv",
        ]

        if is_video:
            if is_ffmpeg_available():
                extracted_wav_path = (
                    Path(tempfile.gettempdir()) / f"mm_audio_{meeting_id}.wav"
                )
                temp_files_to_cleanup.append(extracted_wav_path)
                logger.info(
                    "Extracting audio from video file %s via FFmpeg...", input_media_path
                )
                try:
                    await extract_audio_from_video(input_media_path, extracted_wav_path)
                    audio_for_transcription_path = extracted_wav_path
                except Exception as ff_err:
                    logger.warning(
                        "FFmpeg extraction failed (%s). Gracefully falling back to sending video directly to DeepGram.",
                        ff_err,
                    )
                    audio_for_transcription_path = input_media_path
            else:
                logger.warning(
                    "FFmpeg not found in system PATH. Gracefully sending video directly to DeepGram."
                )
                audio_for_transcription_path = input_media_path

        # Execute DeepGram Speech-to-Text & Diarization
        logger.info(
            "Sending audio %s to DeepGram Nova-3 transcription API...",
            str(audio_for_transcription_path),
        )
        transcription_result = await deepgram_service.transcribe_file(
            audio_for_transcription_path
        )

        logger.info(
            "DeepGram completed: duration=%.2fs, speakers=%s, utterances=%d",
            transcription_result.duration_seconds,
            transcription_result.speakers,
            len(transcription_result.utterances),
        )

        # Persist Stage 1 results in DB
        async with async_session_maker() as db:
            now = datetime.now(UTC)

            # Delete existing transcript segments and speakers (will be recreated)
            await db.execute(
                delete(TranscriptSegment).where(
                    TranscriptSegment.meeting_id == meeting_uuid
                )
            )
            await db.execute(
                delete(Speaker).where(Speaker.meeting_id == meeting_uuid)
            )
            await db.flush()

            speaker_map: dict[str, uuid.UUID] = {}
            for label in transcription_result.speakers:
                spk_id = uuid.uuid4()
                speaker_map[label] = spk_id
                # Use raw SQL with ON CONFLICT DO NOTHING to handle any edge cases
                await db.execute(
                    text("""
                        INSERT INTO speakers (id, meeting_id, speaker_label, participant_id, created_at)
                        VALUES (:id, :meeting_id, :speaker_label, :participant_id, :created_at)
                        ON CONFLICT (meeting_id, speaker_label) DO NOTHING
                    """),
                    {
                        "id": spk_id,
                        "meeting_id": meeting_uuid,
                        "speaker_label": label,
                        "participant_id": None,
                        "created_at": now,
                    },
                )
            await db.flush()

            for idx, utt in enumerate(transcription_result.utterances):
                spk_id = speaker_map.get(utt.speaker_label)
                await db.execute(
                    text("""
                        INSERT INTO transcript_segments (id, meeting_id, speaker_id, segment_index, start_time_seconds, end_time_seconds, text, confidence, created_at)
                        VALUES (:id, :meeting_id, :speaker_id, :segment_index, :start_time_seconds, :end_time_seconds, :text, :confidence, :created_at)
                        ON CONFLICT (meeting_id, segment_index) DO NOTHING
                    """),
                    {
                        "id": uuid.uuid4(),
                        "meeting_id": meeting_uuid,
                        "speaker_id": spk_id,
                        "segment_index": idx,
                        "start_time_seconds": utt.start_time_seconds,
                        "end_time_seconds": utt.end_time_seconds,
                        "text": utt.text,
                        "confidence": utt.confidence,
                        "created_at": now,
                    },
                )

            # Update meeting status to analyzing (Stage 2 in progress)
            stmt_m = select(Meeting).where(Meeting.id == meeting_uuid)
            res_m = await db.execute(stmt_m)
            meeting = res_m.scalars().first()
            if meeting:
                meeting.duration_seconds = max(
                    1, int(round(transcription_result.duration_seconds))
                )
                meeting.status = "analyzing"
                meeting.updated_at = now

            # Mark transcription stage completed
            stmt_j = select(ProcessingJob).where(
                ProcessingJob.meeting_id == meeting_uuid,
                ProcessingJob.stage == "transcription",
            )
            res_j = await db.execute(stmt_j)
            job = res_j.scalars().first()
            if job:
                job.status = "completed"
                if job.started_at is None:
                    job.started_at = getattr(job, "created_at", None) or now
                job.completed_at = now

            # Record summarization job as running
            stmt_s = select(ProcessingJob).where(
                ProcessingJob.meeting_id == meeting_uuid,
                ProcessingJob.stage == "summarization",
            )
            res_s = await db.execute(stmt_s)
            sum_job = res_s.scalars().first()
            if sum_job:
                sum_job.status = "running"
                sum_job.started_at = now
                sum_job.completed_at = None
                sum_job.error_message = None
            else:
                sum_job = ProcessingJob(
                    id=uuid.uuid4(),
                    meeting_id=meeting_uuid,
                    stage="summarization",
                    status="running",
                    started_at=now,
                    completed_at=None,
                    created_at=now,
                )
                db.add(sum_job)

            await db.commit()

        # =========================================================================
        # Stage 2: Google Gemini Intelligence Extraction
        # =========================================================================
        logger.info(
            "Starting Stage 2 Gemini intelligence extraction for meeting %s...",
            meeting_id,
        )

        # Build formatted transcript for Gemini context
        formatted_lines = []
        for utt in transcription_result.utterances:
            ts_str = format_seconds_to_timestamp(utt.start_time_seconds)
            formatted_lines.append(f"[{ts_str}] {utt.speaker_label}: {utt.text}")
        formatted_transcript = "\n".join(formatted_lines)

        if not formatted_transcript.strip():
            formatted_transcript = transcription_result.full_transcript or "No spoken content recorded."

        intelligence_result = await gemini_service.extract_meeting_intelligence(
            formatted_transcript
        )

        logger.info(
            "Gemini extraction complete: summary_len=%d, actions=%d, decisions=%d, sentiment=%s",
            len(intelligence_result.summary_short),
            len(intelligence_result.action_items),
            len(intelligence_result.decisions),
            intelligence_result.sentiment,
        )

        # Persist Stage 2 results in DB
        async with async_session_maker() as db:
            now = datetime.now(UTC)

            # Clean prior insights for idempotency
            if KeyPoint:
                await db.execute(
                    delete(KeyPoint).where(KeyPoint.meeting_id == meeting_uuid)
                )
            if ActionItem:
                await db.execute(
                    delete(ActionItem).where(ActionItem.meeting_id == meeting_uuid)
                )
            if Decision:
                await db.execute(
                    delete(Decision).where(Decision.meeting_id == meeting_uuid)
                )
            if UnresolvedIssue:
                await db.execute(
                    delete(UnresolvedIssue).where(
                        UnresolvedIssue.meeting_id == meeting_uuid
                    )
                )
            if FollowUpItem:
                await db.execute(
                    delete(FollowUpItem).where(
                        FollowUpItem.meeting_id == meeting_uuid
                    )
                )
            if Deadline:
                await db.execute(
                    delete(Deadline).where(Deadline.meeting_id == meeting_uuid)
                )

            # Update meeting record with summaries and sentiment
            stmt_m = select(Meeting).where(Meeting.id == meeting_uuid)
            res_m = await db.execute(stmt_m)
            meeting = res_m.scalars().first()
            if meeting:
                meeting.summary_short = intelligence_result.summary_short
                meeting.summary_detailed = intelligence_result.summary_detailed
                meeting.sentiment = intelligence_result.sentiment
                meeting.sentiment_score = intelligence_result.sentiment_score
                meeting.status = "completed"
                meeting.updated_at = now

            # Insert Key Points
            if KeyPoint:
                for kp in intelligence_result.key_points:
                    kp_rec = KeyPoint(
                        id=uuid.uuid4(),
                        meeting_id=meeting_uuid,
                        point_text=kp.point_text,
                        timestamp_seconds=kp.timestamp_seconds,
                        created_at=now,
                    )
                    db.add(kp_rec)

            # Insert Action Items
            if ActionItem:
                for act in intelligence_result.action_items:
                    # Parse deadline_date if provided
                    d_date = None
                    if act.deadline_date:
                        try:
                            d_date = date.fromisoformat(act.deadline_date)
                        except (ValueError, TypeError):
                            d_date = None

                    assigned_uuid = None
                    raw_assigned = getattr(act, "assigned_to", None) or getattr(act, "assignee", None)
                    if raw_assigned:
                        try:
                            assigned_uuid = uuid.UUID(str(raw_assigned))
                        except (ValueError, TypeError):
                            assigned_uuid = None

                    act_rec = ActionItem(
                        id=uuid.uuid4(),
                        meeting_id=meeting_uuid,
                        task_description=act.task_description,
                        assigned_to=assigned_uuid,
                        deadline_raw_text=act.deadline_raw_text,
                        deadline_date=d_date,
                        status="pending",
                        timestamp_seconds=act.timestamp_seconds,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(act_rec)

            # Insert Decisions
            if Decision:
                for dec in intelligence_result.decisions:
                    decided_uuid = None
                    raw_decided = getattr(dec, "decided_by", None)
                    if raw_decided:
                        try:
                            decided_uuid = uuid.UUID(str(raw_decided))
                        except (ValueError, TypeError):
                            decided_uuid = None

                    dec_rec = Decision(
                        id=uuid.uuid4(),
                        meeting_id=meeting_uuid,
                        decision_text=dec.decision_text,
                        decided_by=decided_uuid,
                        timestamp_seconds=dec.timestamp_seconds,
                        created_at=now,
                    )
                    db.add(dec_rec)

            # Insert Unresolved Issues
            if UnresolvedIssue:
                for iss in intelligence_result.unresolved_issues:
                    iss_rec = UnresolvedIssue(
                        id=uuid.uuid4(),
                        meeting_id=meeting_uuid,
                        issue_text=iss.issue_text,
                        timestamp_seconds=iss.timestamp_seconds,
                        created_at=now,
                    )
                    db.add(iss_rec)

            # Insert Follow Up Items
            if FollowUpItem:
                for fol in intelligence_result.follow_up_items:
                    fol_rec = FollowUpItem(
                        id=uuid.uuid4(),
                        meeting_id=meeting_uuid,
                        description=fol.description,
                        timestamp_seconds=fol.timestamp_seconds,
                        created_at=now,
                    )
                    db.add(fol_rec)

            # Insert Deadlines
            if Deadline:
                for dl in intelligence_result.deadlines:
                    dl_date = None
                    if dl.resolved_date:
                        try:
                            dl_date = date.fromisoformat(dl.resolved_date)
                        except (ValueError, TypeError):
                            dl_date = None

                    dl_rec = Deadline(
                        id=uuid.uuid4(),
                        meeting_id=meeting_uuid,
                        description=dl.description,
                        raw_text=dl.raw_text,
                        resolved_date=dl_date,
                        timestamp_seconds=dl.timestamp_seconds,
                        created_at=now,
                    )
                    db.add(dl_rec)

            # Update all processing jobs to completed
            stages = [
                "summarization",
                "action_item_extraction",
                "decision_extraction",
                "deadline_detection",
            ]
            for stg in stages:
                stmt_sj = select(ProcessingJob).where(
                    ProcessingJob.meeting_id == meeting_uuid,
                    ProcessingJob.stage == stg,
                )
                res_sj = await db.execute(stmt_sj)
                pj = res_sj.scalars().first()
                if pj:
                    pj.status = "completed"
                    if pj.started_at is None:
                        pj.started_at = getattr(pj, "created_at", None) or now
                    pj.completed_at = now
                else:
                    pj = ProcessingJob(
                        id=uuid.uuid4(),
                        meeting_id=meeting_uuid,
                        stage=stg,
                        status="completed",
                        started_at=now,
                        completed_at=now,
                        created_at=now,
                    )
                    db.add(pj)

            await db.commit()

        logger.info(
            "Successfully completed full AI processing (Stage 1 + Stage 2) for meeting_id=%s",
            meeting_id,
        )

        return {
            "status": "success",
            "meeting_id": meeting_id,
            "meeting_status": "completed",
            "duration_seconds": transcription_result.duration_seconds,
            "speakers_count": len(transcription_result.speakers),
            "segments_count": len(transcription_result.utterances),
            "key_points_count": len(intelligence_result.key_points),
            "action_items_count": len(intelligence_result.action_items),
            "decisions_count": len(intelligence_result.decisions),
            "sentiment": intelligence_result.sentiment,
            "sentiment_score": intelligence_result.sentiment_score,
        }

    except Exception as exc:
        logger.error(
            "Error in AI pipeline for meeting %s: %s",
            meeting_id,
            str(exc),
            exc_info=True,
        )

        # Record failure state in database
        try:
            async with async_session_maker() as db:
                now = datetime.now(UTC)
                stmt_m = select(models.Meeting).where(models.Meeting.id == meeting_uuid)
                res_m = await db.execute(stmt_m)
                meeting = res_m.scalars().first()
                if meeting:
                    meeting.status = "failed"
                    meeting.failure_reason = str(exc)[:500]
                    meeting.updated_at = now

                # Mark all running processing jobs as failed
                stmt_j = select(models.ProcessingJob).where(
                    models.ProcessingJob.meeting_id == meeting_uuid,
                    models.ProcessingJob.status.in_(["running", "queued"]),
                )
                res_j = await db.execute(stmt_j)
                failed_jobs = res_j.scalars().all()
                for fj in failed_jobs:
                    fj.status = "failed"
                    fj.error_message = str(exc)[:500]
                    if fj.started_at is None:
                        fj.started_at = getattr(fj, "created_at", None) or now
                    fj.completed_at = now

                await db.commit()
        except Exception as db_exc:
            logger.error("Failed to record failure state in database: %s", str(db_exc))

        raise

    finally:
        for temp_p in temp_files_to_cleanup:
            if temp_p.exists():
                try:
                    temp_p.unlink()
                except OSError as err:
                    logger.debug("Failed to remove temp file %s: %s", temp_p, err)


class WorkerSettings:
    """arq Worker configuration."""

    functions: list[Any] = [process_meeting]
    redis_settings = (
        RedisSettings.from_dsn(settings.REDIS_URL) if RedisSettings else None
    )
    on_startup = startup
    on_shutdown = shutdown
    max_tries: int = 3
    job_timeout: int = 3600
    retry_delay: int = 10
