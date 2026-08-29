"""Dashboard service handling analytics, widgets aggregation, and global search."""

import uuid
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import models
from app.modules.dashboard.schemas import (
    ActionStats,
    DashboardStatsResponse,
    GlobalSearchResult,
    RecentDecisionItem,
    RecentMeetingItem,
    SentimentBreakdown,
    UpcomingDeadlineItem,
)
from app.modules.insights.models import (
    get_action_item_model,
    get_decision_model,
)
from app.modules.meetings.models import get_meeting_model
from app.modules.transcripts.models import get_transcript_segment_model


class DashboardService:
    """Service providing dashboard metrics, widget feeds, and cross-meeting search."""

    @staticmethod
    async def get_stats(db: AsyncSession, current_user: Any) -> DashboardStatsResponse:
        """Calculates aggregated meeting, duration, action item, decision, and sentiment stats."""
        user_uuid = uuid.UUID(str(current_user.id))
        Meeting = get_meeting_model()
        ActionItem = get_action_item_model()
        Decision = get_decision_model()

        # 1. Fetch user's meetings
        stmt_m = select(Meeting).where(Meeting.owner_id == user_uuid)
        res_m = await db.execute(stmt_m)
        meetings = res_m.scalars().all()

        total_meetings = len(meetings)
        total_duration_sec = sum(int(m.duration_seconds or 0) for m in meetings)
        total_duration_min = int(round(total_duration_sec / 60.0))
        total_hours_formatted = f"{total_duration_sec / 3600.0:.1f} hrs"

        # Sentiment counts
        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0, "mixed": 0}
        for m in meetings:
            sent = str(m.sentiment or "").lower()
            if sent in sentiment_counts:
                sentiment_counts[sent] += 1

        meeting_ids = [m.id for m in meetings]
        if not meeting_ids:
            return DashboardStatsResponse(
                total_meetings=0,
                total_duration_seconds=0,
                total_duration_minutes=0,
                total_hours_formatted="0.0 hrs",
                total_decisions=0,
                action_items=ActionStats(),
                sentiment=SentimentBreakdown(),
            )

        # 2. Fetch action items stats
        stmt_act = select(ActionItem).where(ActionItem.meeting_id.in_(meeting_ids))
        res_act = await db.execute(stmt_act)
        actions = res_act.scalars().all()

        act_stats = ActionStats(
            total=len(actions),
            pending=sum(1 for a in actions if a.status == "pending"),
            in_progress=sum(1 for a in actions if a.status == "in_progress"),
            completed=sum(1 for a in actions if a.status == "completed"),
            overdue=sum(1 for a in actions if a.status == "overdue"),
        )

        # 3. Fetch decisions count
        stmt_dec = select(func.count(Decision.id)).where(Decision.meeting_id.in_(meeting_ids))
        res_dec = await db.execute(stmt_dec)
        total_decisions = res_dec.scalar() or 0

        return DashboardStatsResponse(
            total_meetings=total_meetings,
            total_duration_seconds=total_duration_sec,
            total_duration_minutes=total_duration_min,
            total_hours_formatted=total_hours_formatted,
            total_decisions=total_decisions,
            action_items=act_stats,
            sentiment=SentimentBreakdown(**sentiment_counts),
        )

    @staticmethod
    async def get_upcoming_deadlines(
        db: AsyncSession, current_user: Any, limit: int = 10
    ) -> list[UpcomingDeadlineItem]:
        """Retrieves upcoming deadlines across all meetings owned by the user."""
        user_uuid = uuid.UUID(str(current_user.id))
        Meeting = get_meeting_model()
        Deadline = models.Deadline

        if Deadline is None:
            return []

        stmt = (
            select(Deadline, Meeting.title.label("meeting_title"))
            .join(Meeting, Deadline.meeting_id == Meeting.id)
            .where(Meeting.owner_id == user_uuid)
            .order_by(Deadline.resolved_date.asc().nullslast(), desc(Deadline.created_at))
            .limit(limit)
        )
        res = await db.execute(stmt)
        rows = res.all()

        items = []
        for dl, m_title in rows:
            items.append(
                UpcomingDeadlineItem(
                    id=str(dl.id),
                    meeting_id=str(dl.meeting_id),
                    meeting_title=m_title or "Untitled Meeting",
                    description=dl.description or dl.raw_text or "Deadline",
                    raw_text=dl.raw_text,
                    resolved_date=dl.resolved_date,
                    timestamp_seconds=(
                        float(dl.timestamp_seconds) if dl.timestamp_seconds is not None else None
                    ),
                    created_at=dl.created_at,
                )
            )
        return items

    @staticmethod
    async def get_recent_decisions(
        db: AsyncSession, current_user: Any, limit: int = 10
    ) -> list[RecentDecisionItem]:
        """Retrieves recent decisions across all meetings owned by the user."""
        user_uuid = uuid.UUID(str(current_user.id))
        Meeting = get_meeting_model()
        Decision = get_decision_model()

        stmt = (
            select(Decision, Meeting.title.label("meeting_title"))
            .join(Meeting, Decision.meeting_id == Meeting.id)
            .where(Meeting.owner_id == user_uuid)
            .order_by(desc(Decision.created_at))
            .limit(limit)
        )
        res = await db.execute(stmt)
        rows = res.all()

        return [
            RecentDecisionItem(
                id=str(dec.id),
                meeting_id=str(dec.meeting_id),
                meeting_title=m_title or "Untitled Meeting",
                decision_text=dec.decision_text,
                decided_by=str(dec.decided_by) if dec.decided_by else None,
                timestamp_seconds=(
                    float(dec.timestamp_seconds) if dec.timestamp_seconds is not None else None
                ),
                created_at=dec.created_at,
            )
            for dec, m_title in rows
        ]

    @staticmethod
    async def get_recent_meetings(
        db: AsyncSession, current_user: Any, limit: int = 10
    ) -> list[RecentMeetingItem]:
        """Retrieves enriched recent meetings list with action item and decision counts."""
        user_uuid = uuid.UUID(str(current_user.id))
        Meeting = get_meeting_model()
        ActionItem = get_action_item_model()
        Decision = get_decision_model()

        stmt_m = (
            select(Meeting)
            .where(Meeting.owner_id == user_uuid)
            .order_by(desc(Meeting.created_at))
            .limit(limit)
        )
        res_m = await db.execute(stmt_m)
        meetings = res_m.scalars().all()

        result = []
        for m in meetings:
            # Action items count
            stmt_a = select(func.count(ActionItem.id)).where(ActionItem.meeting_id == m.id)
            res_a = await db.execute(stmt_a)
            actions_count = res_a.scalar() or 0

            # Decisions count
            stmt_d = select(func.count(Decision.id)).where(Decision.meeting_id == m.id)
            res_d = await db.execute(stmt_d)
            decisions_count = res_d.scalar() or 0

            result.append(
                RecentMeetingItem(
                    id=str(m.id),
                    title=m.title,
                    meeting_date=m.meeting_date,
                    duration_seconds=int(m.duration_seconds or 0),
                    status=m.status,
                    summary_short=m.summary_short,
                    sentiment=m.sentiment,
                    sentiment_score=(
                        float(m.sentiment_score) if m.sentiment_score is not None else None
                    ),
                    action_items_count=actions_count,
                    decisions_count=decisions_count,
                    created_at=m.created_at,
                )
            )
        return result

    @staticmethod
    async def global_search(
        db: AsyncSession, query: str, current_user: Any, limit: int = 15
    ) -> GlobalSearchResult:
        """Searches across user's meetings (title, summary), transcripts, action items, and decisions."""
        user_uuid = uuid.UUID(str(current_user.id))
        clean_q = query.strip()
        if not clean_q:
            return GlobalSearchResult(query=query)

        search_pattern = f"%{clean_q}%"
        Meeting = get_meeting_model()
        TranscriptSegment = get_transcript_segment_model()
        ActionItem = get_action_item_model()
        Decision = get_decision_model()

        # 1. Search Meetings
        stmt_m = (
            select(Meeting)
            .where(
                Meeting.owner_id == user_uuid,
                or_(
                    Meeting.title.ilike(search_pattern),
                    Meeting.summary_short.ilike(search_pattern),
                    Meeting.summary_detailed.ilike(search_pattern),
                ),
            )
            .limit(limit)
        )
        res_m = await db.execute(stmt_m)
        matched_meetings = [
            {
                "id": str(m.id),
                "title": m.title,
                "summary_short": m.summary_short,
                "status": m.status,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in res_m.scalars().all()
        ]

        # 2. Search Transcripts
        stmt_t = (
            select(TranscriptSegment, Meeting.title.label("meeting_title"))
            .join(Meeting, TranscriptSegment.meeting_id == Meeting.id)
            .where(Meeting.owner_id == user_uuid, TranscriptSegment.text.ilike(search_pattern))
            .limit(limit)
        )
        res_t = await db.execute(stmt_t)
        matched_transcripts = [
            {
                "id": str(seg.id),
                "meeting_id": str(seg.meeting_id),
                "meeting_title": m_title,
                "text": seg.text,
                "start_time_seconds": float(seg.start_time_seconds),
                "end_time_seconds": float(seg.end_time_seconds),
            }
            for seg, m_title in res_t.all()
        ]

        # 3. Search Action Items
        stmt_a = (
            select(ActionItem, Meeting.title.label("meeting_title"))
            .join(Meeting, ActionItem.meeting_id == Meeting.id)
            .where(
                Meeting.owner_id == user_uuid,
                or_(
                    ActionItem.task_description.ilike(search_pattern),
                    ActionItem.deadline_raw_text.ilike(search_pattern),
                ),
            )
            .limit(limit)
        )
        res_a = await db.execute(stmt_a)
        matched_actions = [
            {
                "id": str(act.id),
                "meeting_id": str(act.meeting_id),
                "meeting_title": m_title,
                "task_description": act.task_description,
                "status": act.status,
                "deadline_raw_text": act.deadline_raw_text,
                "timestamp_seconds": (
                    float(act.timestamp_seconds) if act.timestamp_seconds is not None else None
                ),
            }
            for act, m_title in res_a.all()
        ]

        # 4. Search Decisions
        stmt_d = (
            select(Decision, Meeting.title.label("meeting_title"))
            .join(Meeting, Decision.meeting_id == Meeting.id)
            .where(Meeting.owner_id == user_uuid, Decision.decision_text.ilike(search_pattern))
            .limit(limit)
        )
        res_d = await db.execute(stmt_d)
        matched_decisions = [
            {
                "id": str(dec.id),
                "meeting_id": str(dec.meeting_id),
                "meeting_title": m_title,
                "decision_text": dec.decision_text,
                "timestamp_seconds": (
                    float(dec.timestamp_seconds) if dec.timestamp_seconds is not None else None
                ),
            }
            for dec, m_title in res_d.all()
        ]

        total_matches = (
            len(matched_meetings)
            + len(matched_transcripts)
            + len(matched_actions)
            + len(matched_decisions)
        )

        return GlobalSearchResult(
            query=query,
            total_matches=total_matches,
            meetings=matched_meetings,
            transcripts=matched_transcripts,
            action_items=matched_actions,
            decisions=matched_decisions,
        )
