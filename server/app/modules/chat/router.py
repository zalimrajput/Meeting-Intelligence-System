"""Chat HTTP router for Meeting Q&A."""

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_guard import get_current_user
from app.modules.auth.schemas import ApiResponse
from app.modules.qa.schemas import (
    AskQuestionRequest,
    ChatMessageResponse,
)
from app.modules.qa.service import QAService

router = APIRouter(prefix="/meetings", tags=["Meeting Q&A"])


@router.post(
    "/{meeting_id}/chat",
    response_model=ApiResponse[ChatMessageResponse],
    status_code=status.HTTP_200_OK,
    summary="Ask AI a question about a meeting (RAG with transcript & timestamp citations)",
)
@router.post(
    "/{meeting_id}/qa",
    response_model=ApiResponse[ChatMessageResponse],
    status_code=status.HTTP_200_OK,
    summary="Ask AI a question about a meeting (alias)",
    include_in_schema=False,
)
async def ask_meeting_question(
    meeting_id: str,
    payload: AskQuestionRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ChatMessageResponse]:
    """Answers a question about the meeting using Gemini with transcript context."""
    response = await QAService.ask_question(
        db=db,
        meeting_id=meeting_id,
        question=payload.question,
        current_user=current_user,
    )
    return ApiResponse(success=True, data=response)


@router.post(
    "/{meeting_id}/chat/stream",
    summary="Stream AI answer about a meeting (Server-Sent Events / SSE)",
)
async def stream_meeting_question(
    meeting_id: str,
    payload: AskQuestionRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Streams the AI answer token by token using SSE."""
    event_generator = QAService.stream_question_response(
        db=db,
        meeting_id=meeting_id,
        question=payload.question,
        current_user=current_user,
    )
    return StreamingResponse(
        event_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{meeting_id}/chat",
    response_model=ApiResponse[list[ChatMessageResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get Q&A chat conversation history for a meeting",
)
@router.get(
    "/{meeting_id}/chat/history",
    response_model=ApiResponse[list[ChatMessageResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get Q&A chat conversation history for a meeting (history alias)",
    include_in_schema=False,
)
@router.get(
    "/{meeting_id}/qa",
    response_model=ApiResponse[list[ChatMessageResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get Q&A chat conversation history for a meeting (qa alias)",
    include_in_schema=False,
)
async def get_chat_history(
    meeting_id: str,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ChatMessageResponse]]:
    """Retrieves chronological chat conversation history."""
    history = await QAService.get_chat_history(
        db=db,
        meeting_id=meeting_id,
        current_user=current_user,
    )
    return ApiResponse(success=True, data=history)
