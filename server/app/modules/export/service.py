"""Export service providing multi-format meeting intelligence exports (Markdown, JSON, Text, Email Briefing)."""

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import models
from app.middleware.error_handler import AppError
from app.modules.insights.models import (
    get_action_item_model,
    get_decision_model,
    get_key_point_model,
    get_unresolved_issue_model,
)
from app.modules.meetings.models import get_meeting_model
from app.modules.transcripts.models import get_speaker_model, get_transcript_segment_model


def format_seconds(seconds: float) -> str:
    """Formats float seconds into HH:MM:SS or MM:SS format."""
    total_secs = int(seconds)
    hours = total_secs // 3600
    mins = (total_secs % 3600) // 60
    secs = total_secs % 60
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"



class ExportService:
    """Service generating formatted meeting exports."""

    @staticmethod
    async def _fetch_meeting_data(
        db: AsyncSession, meeting_id: str, current_user: Any
    ) -> dict[str, Any]:
        """Fetches and verifies all meeting data, insights, and transcripts."""
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            raise AppError(status_code=400, code="INVALID_ID", message="Invalid meeting ID.") from None

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
                message="You do not have permission to export this meeting.",
            )

        # Fetch all related entities
        ActionItem = get_action_item_model()
        Decision = get_decision_model()
        KeyPoint = get_key_point_model()
        UnresolvedIssue = get_unresolved_issue_model()
        TranscriptSegment = get_transcript_segment_model()
        Speaker = get_speaker_model()
        Deadline = models.Deadline

        # Action Items
        res_a = await db.execute(
            select(ActionItem).where(ActionItem.meeting_id == meeting_uuid).order_by(asc(ActionItem.created_at))
        )
        actions = res_a.scalars().all()

        # Decisions
        res_d = await db.execute(
            select(Decision).where(Decision.meeting_id == meeting_uuid).order_by(asc(Decision.created_at))
        )
        decisions = res_d.scalars().all()

        # Key Points
        res_k = await db.execute(
            select(KeyPoint).where(KeyPoint.meeting_id == meeting_uuid).order_by(asc(KeyPoint.created_at))
        )
        key_points = res_k.scalars().all()

        # Unresolved Issues
        res_u = await db.execute(
            select(UnresolvedIssue).where(UnresolvedIssue.meeting_id == meeting_uuid).order_by(asc(UnresolvedIssue.created_at))
        )
        issues = res_u.scalars().all()

        # Deadlines
        deadlines = []
        if Deadline is not None:
            res_dl = await db.execute(
                select(Deadline).where(Deadline.meeting_id == meeting_uuid).order_by(asc(Deadline.created_at))
            )
            deadlines = res_dl.scalars().all()

        # Speakers
        speaker_map: dict[str, str] = {}
        if Speaker is not None:
            res_s = await db.execute(
                select(Speaker).where(Speaker.meeting_id == meeting_uuid)
            )
            speakers = res_s.scalars().all()
            for s in speakers:
                speaker_map[str(s.id)] = s.speaker_label


        # Transcripts
        res_t = await db.execute(
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_uuid)
            .order_by(asc(TranscriptSegment.segment_index))
        )
        transcript_segments = res_t.scalars().all()

        return {
            "meeting": meeting,
            "actions": actions,
            "decisions": decisions,
            "key_points": key_points,
            "issues": issues,
            "deadlines": deadlines,
            "speaker_map": speaker_map,
            "transcripts": transcript_segments,
        }

    @staticmethod
    async def export_markdown(db: AsyncSession, meeting_id: str, current_user: Any) -> tuple[str, str]:
        """Generates a complete GitHub Flavored Markdown document."""
        data = await ExportService._fetch_meeting_data(db, meeting_id, current_user)
        m = data["meeting"]
        created_str = m.created_at.strftime("%Y-%m-%d %H:%M UTC") if m.created_at else "N/A"
        duration_min = round(int(m.duration_seconds or 0) / 60.0, 1)

        lines = [
            f"# {m.title or 'Meeting Intelligence Report'}",
            "",
            f"**Date:** {created_str} | **Duration:** {duration_min} minutes | **Sentiment:** {m.sentiment or 'Neutral'} ({m.sentiment_score or 0.0})",
            "",
            "## 📋 Executive Summary",
            f"{m.summary_short or 'No summary available.'}",
            "",
            "### Detailed Summary",
            f"{m.summary_detailed or m.summary_short or 'N/A'}",
            "",
            "## 🔑 Key Points",
        ]

        if data["key_points"]:
            for kp in data["key_points"]:
                ts = f" `[{format_seconds(float(kp.timestamp_seconds))}]`" if kp.timestamp_seconds is not None else ""
                lines.append(f"- {kp.point_text}{ts}")
        else:
            lines.append("- No key points recorded.")

        lines.extend([
            "",
            "## 🎯 Action Items",
            "",
            "| Task Description | Owner | Deadline | Status | Timestamp |",
            "| :--- | :--- | :--- | :---: | :---: |",
        ])

        if data["actions"]:
            for act in data["actions"]:
                ts = format_seconds(float(act.timestamp_seconds)) if act.timestamp_seconds is not None else "N/A"
                owner = str(act.assigned_to) if getattr(act, "assigned_to", None) else "Unassigned"
                dl = act.deadline_raw_text or str(act.deadline_date or "N/A")
                lines.append(f"| {act.task_description} | {owner} | {dl} | **{act.status}** | `{ts}` |")
        else:
            lines.append("| *No action items recorded* | - | - | - | - |")

        lines.extend([
            "",
            "## ⚖️ Decisions Made",
        ])

        if data["decisions"]:
            for dec in data["decisions"]:
                ts = f" `[{format_seconds(float(dec.timestamp_seconds))}]`" if dec.timestamp_seconds is not None else ""
                lines.append(f"- **{dec.decision_text}**{ts}")
        else:
            lines.append("- No decisions recorded.")

        if data["issues"]:
            lines.extend(["", "## ⚠️ Unresolved Issues"])
            for issue in data["issues"]:
                lines.append(f"- {issue.issue_text}")

        lines.extend([
            "",
            "## 🎙️ Diarized Transcript",
            "",
        ])

        if data["transcripts"]:
            for seg in data["transcripts"]:
                spk = data["speaker_map"].get(str(seg.speaker_id), "Speaker") if seg.speaker_id else "Speaker"
                ts = format_seconds(float(seg.start_time_seconds))
                lines.append(f"**`[{ts}]` {spk}:** {seg.text}\n")
        else:
            lines.append("*No transcript segments available.*")

        filename = f"meeting_{m.id}_{datetime.now().strftime('%Y%m%d')}.md"
        return "\n".join(lines), filename

    @staticmethod
    async def export_json(db: AsyncSession, meeting_id: str, current_user: Any) -> tuple[str, str]:
        """Generates a structured JSON string export."""
        data = await ExportService._fetch_meeting_data(db, meeting_id, current_user)
        m = data["meeting"]

        export_obj = {
            "id": str(m.id),
            "title": m.title,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "duration_seconds": int(m.duration_seconds or 0),
            "status": m.status,
            "sentiment": m.sentiment,
            "sentiment_score": float(m.sentiment_score) if m.sentiment_score is not None else None,
            "summary_short": m.summary_short,
            "summary_detailed": m.summary_detailed,
            "key_points": [
                {
                    "point_text": kp.point_text,
                    "timestamp_seconds": float(kp.timestamp_seconds) if kp.timestamp_seconds is not None else None,
                }
                for kp in data["key_points"]
            ],
            "action_items": [
                {
                    "id": str(a.id),
                    "task_description": a.task_description,
                    "assigned_to": str(a.assigned_to) if getattr(a, "assigned_to", None) else None,
                    "deadline_raw_text": a.deadline_raw_text,
                    "deadline_date": a.deadline_date.isoformat() if a.deadline_date else None,
                    "status": a.status,
                    "timestamp_seconds": float(a.timestamp_seconds) if a.timestamp_seconds is not None else None,
                }
                for a in data["actions"]
            ],
            "decisions": [
                {
                    "id": str(d.id),
                    "decision_text": d.decision_text,
                    "timestamp_seconds": float(d.timestamp_seconds) if d.timestamp_seconds is not None else None,
                }
                for d in data["decisions"]
            ],
            "transcript_segments": [
                {
                    "speaker": data["speaker_map"].get(str(t.speaker_id), "Speaker"),
                    "start_time_seconds": float(t.start_time_seconds),
                    "end_time_seconds": float(t.end_time_seconds),
                    "text": t.text,
                }
                for t in data["transcripts"]
            ],
        }

        filename = f"meeting_{m.id}_{datetime.now().strftime('%Y%m%d')}.json"
        return json.dumps(export_obj, indent=2), filename

    @staticmethod
    async def export_email_digest(db: AsyncSession, meeting_id: str, current_user: Any) -> tuple[str, str]:
        """Generates a formatted Executive Email Briefing."""
        data = await ExportService._fetch_meeting_data(db, meeting_id, current_user)
        m = data["meeting"]
        created_str = m.created_at.strftime("%B %d, %Y") if m.created_at else "Today"

        lines = [
            f"Subject: [Executive Briefing] {m.title or 'Team Meeting'} Summary & Action Items ({created_str})",
            "",
            "Hi Team,",
            "",
            f"Here is the executive summary and action item digest from our meeting: '{m.title or 'Meeting'}'.",
            "",
            "============================================================",
            "EXECUTIVE SUMMARY",
            "============================================================",
            f"{m.summary_short or 'N/A'}",
            "",
            "============================================================",
            "ACTION ITEMS & DELIVERABLES",
            "============================================================",
        ]

        if data["actions"]:
            for idx, act in enumerate(data["actions"], 1):
                owner = str(act.assigned_to) if getattr(act, "assigned_to", None) else "Unassigned"
                dl = act.deadline_raw_text or str(act.deadline_date or "ASAP")
                lines.append(f"{idx}. [{act.status.upper()}] {act.task_description}")
                lines.append(f"   Owner: {owner} | Due: {dl}")

        else:
            lines.append("No pending action items.")

        lines.extend([
            "",
            "============================================================",
            "KEY DECISIONS MADE",
            "============================================================",
        ])

        if data["decisions"]:
            for idx, dec in enumerate(data["decisions"], 1):
                lines.append(f"{idx}. {dec.decision_text}")
        else:
            lines.append("No explicit decisions recorded.")

        lines.extend([
            "",
            "Best regards,",
            f"{current_user.full_name or 'MeetingMind AI'}",
        ])

        filename = f"email_briefing_{m.id}_{datetime.now().strftime('%Y%m%d')}.txt"
        return "\n".join(lines), filename

    @staticmethod
    async def export_text(db: AsyncSession, meeting_id: str, current_user: Any) -> tuple[str, str]:
        """Generates a formatted plain text summary."""
        md_text, filename = await ExportService.export_markdown(db, meeting_id, current_user)
        clean_filename = filename.replace(".md", ".txt")
        return md_text, clean_filename
