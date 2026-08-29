"""Chat service for managing meeting AI conversation history."""

import uuid
from typing import Any

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.error_handler import AppError
from app.modules.chat.models import get_ai_conversation_model
from app.modules.chat.schemas import ChatMessageResponse
from app.modules.meetings.models import get_meeting_model


class ChatService:
    """Service handling meeting conversation history."""

    @staticmethod
    async def get_chat_history(
        db: AsyncSession,
        meeting_id: str,
        current_user: Any,
    ) -> list[ChatMessageResponse]:
        """Retrieves conversational history for a meeting owned by current user."""
        try:
            meeting_uuid = uuid.UUID(meeting_id)
        except (ValueError, TypeError):
            raise AppError(
                status_code=400,
                code="INVALID_ID",
                message="Invalid meeting ID.",
            ) from None

        Meeting = get_meeting_model()
        stmt = select(Meeting).where(Meeting.id == meeting_uuid)
        res = await db.execute(stmt)
        meeting = res.scalars().first()

        if not meeting:
            raise AppError(status_code=404, code="MEETING_NOT_FOUND", message="Meeting not found.")

        if str(meeting.owner_id) != str(current_user.id):
            raise AppError(
                status_code=403,
                code="FORBIDDEN_RESOURCE",
                message="You do not have access to this meeting's chat history.",
            )

        AIConversation = get_ai_conversation_model()
        stmt_c = (
            select(AIConversation)
            .where(AIConversation.meeting_id == meeting_uuid)
            .order_by(asc(AIConversation.created_at))
        )
        res_c = await db.execute(stmt_c)
        convs = res_c.scalars().all()

        return [
            ChatMessageResponse(
                id=str(c.id),
                meeting_id=str(c.meeting_id),
                user_id=str(c.user_id),
                question=c.question,
                answer=c.answer,
                referenced_timestamp_seconds=(
                    float(c.referenced_timestamp_seconds)
                    if c.referenced_timestamp_seconds is not None
                    else None
                ),
                created_at=c.created_at,
            )
            for c in convs
        ]
