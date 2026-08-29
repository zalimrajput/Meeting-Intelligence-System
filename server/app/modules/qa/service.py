"""Meeting Q&A service handling contextual RAG queries over meeting transcripts with Gemini."""

import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.middleware.error_handler import AppError
from app.modules.meetings.models import get_meeting_model
from app.modules.qa.models import get_ai_conversation_model
from app.modules.qa.schemas import ChatMessageResponse
from app.modules.transcripts.models import get_speaker_model, get_transcript_segment_model

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def format_seconds(seconds: float) -> str:
    """Formats float seconds into HH:MM:SS or MM:SS format."""
    total_secs = int(seconds)
    hours = total_secs // 3600
    mins = (total_secs % 3600) // 60
    secs = total_secs % 60
    if hours > 0:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"



def parse_timestamp_from_text(text: str) -> float | None:
    """Extracts first timestamp in [HH:MM:SS] or [MM:SS] format from text and returns float seconds."""
    match_hms = re.search(r"\[(\d{1,2}):(\d{2}):(\d{2})\]", text)
    if match_hms:
        hrs = int(match_hms.group(1))
        mins = int(match_hms.group(2))
        secs = int(match_hms.group(3))
        return float(hrs * 3600 + mins * 60 + secs)

    match_ms = re.search(r"\[(\d{1,3}):(\d{2})\]", text)
    if match_ms:
        mins = int(match_ms.group(1))
        secs = int(match_ms.group(2))
        return float(mins * 60 + secs)
    return None



class QAService:
    """Service handling meeting contextual Q&A and conversation history."""

    @staticmethod
    async def _get_meeting_context(
        db: AsyncSession, meeting_id: str, current_user: Any
    ) -> tuple[uuid.UUID, Any, str]:
        """Verifies access and constructs formatted meeting context text."""
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
                message="You do not have access to this meeting.",
            )

        TranscriptSegment = get_transcript_segment_model()
        Speaker = get_speaker_model()

        stmt_t = (
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_uuid)
            .order_by(asc(TranscriptSegment.segment_index))
        )
        res_t = await db.execute(stmt_t)
        segments = res_t.scalars().all()

        speaker_map: dict[str, str] = {}
        if Speaker is not None:
            stmt_s = select(Speaker).where(Speaker.meeting_id == meeting_uuid)
            res_s = await db.execute(stmt_s)
            speakers = res_s.scalars().all()
            for s in speakers:
                speaker_map[str(s.id)] = s.speaker_label

        lines = [
            f"Meeting Title: {meeting.title}",
            f"Summary: {meeting.summary_short or 'N/A'}",
            "\n--- DIARIZED TRANSCRIPT WITH TIMESTAMPS ---",
        ]
        for seg in segments:
            spk_label = speaker_map.get(str(seg.speaker_id), "Speaker") if seg.speaker_id else "Speaker"
            ts = format_seconds(float(seg.start_time_seconds))
            lines.append(f"[{ts}] {spk_label}: {seg.text}")

        context_text = "\n".join(lines)
        return meeting_uuid, meeting, context_text

    @staticmethod
    async def _call_gemini_api(payload: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
        """Direct call to Gemini REST API."""
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")

        models_to_try = [
            "gemini-2.5-flash",
            "gemini-3.5-flash",
            "gemini-flash-latest",
        ]
        last_error = None

        for current_model in models_to_try:
            url = f"{GEMINI_API_BASE}/{current_model}:generateContent?key={api_key}"
            max_retries = 2
            backoff = 2.0

            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                    last_error = f"Gemini Q&A network/timeout error on {current_model}: {net_err}"
                    logger.warning(
                        "Gemini Q&A request timed out or network error on %s (attempt %d/%d): %s",
                        current_model,
                        attempt + 1,
                        max_retries,
                        net_err,
                    )
                    import asyncio
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                    continue

                if response.status_code == 200:
                    return response.json()

                if response.status_code in [429, 503]:
                    last_error = f"Gemini Q&A {response.status_code} on {current_model}: {response.text}"
                    logger.warning(
                        "Gemini Q&A API returned %d on %s (attempt %d/%d). Retrying or trying next model...",
                        response.status_code,
                        current_model,
                        attempt + 1,
                        max_retries,
                    )
                    import asyncio
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                    continue
                elif response.status_code == 404:
                    last_error = f"Model {current_model} not found (404)."
                    break
                else:
                    logger.error("Gemini Q&A error (%s, %d): %s", current_model, response.status_code, response.text)
                    last_error = f"Gemini API returned status {response.status_code}: {response.text}"
                    break

        raise RuntimeError(last_error or "All Gemini models failed for Q&A.")

    @staticmethod
    async def ask_question(
        db: AsyncSession,
        meeting_id: str,
        question: str,
        current_user: Any,
    ) -> ChatMessageResponse:
        """Asks Gemini a question grounded in the meeting transcript and saves the exchange."""
        meeting_uuid, _, context = await QAService._get_meeting_context(db, meeting_id, current_user)

        prompt = f"""You are MeetingMind AI, an intelligent meeting assistant.
Answer the user's question accurately and concisely based strictly on the provided meeting transcript and summary.

Context:
\"\"\"
{context}
\"\"\"

User Question: {question}

Instructions:
1. Base your answer ONLY on facts stated in the transcript and summary.
2. ALWAYS cite the exact spoken timestamp (e.g. '[02:15]') whenever referencing who said what.
3. If the answer cannot be found in the meeting content, clearly state: "This topic was not discussed in the meeting."
4. Provide direct, helpful, and professional answers.
"""

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
            },
        }

        res_json = await QAService._call_gemini_api(payload)
        candidates = res_json.get("candidates", [])
        if not candidates or not candidates[0].get("content", {}).get("parts", []):
            raise RuntimeError("Gemini returned an empty response.")

        answer_text = candidates[0]["content"]["parts"][0].get("text", "").strip()
        ref_seconds = parse_timestamp_from_text(answer_text)


        # Save to ai_conversations table
        AIConversation = get_ai_conversation_model()
        now = datetime.now(UTC)
        conv_id = uuid.uuid4()
        user_uuid = uuid.UUID(str(current_user.id))

        conv_rec = AIConversation(
            id=conv_id,
            meeting_id=meeting_uuid,
            user_id=user_uuid,
            question=question,
            answer=answer_text,
            referenced_timestamp_seconds=ref_seconds,
            created_at=now,
        )
        db.add(conv_rec)
        await db.commit()

        return ChatMessageResponse(
            id=str(conv_id),
            meeting_id=str(meeting_uuid),
            user_id=str(user_uuid),
            question=question,
            answer=answer_text,
            referenced_timestamp_seconds=ref_seconds,
            created_at=now,
        )

    @staticmethod
    async def stream_question_response(
        db: AsyncSession,
        meeting_id: str,
        question: str,
        current_user: Any,
    ) -> AsyncGenerator[str, None]:
        """Streams tokens from Gemini API via Server-Sent Events (SSE) and saves conversation at completion."""
        meeting_uuid, _, context = await QAService._get_meeting_context(db, meeting_id, current_user)

        prompt = f"""You are MeetingMind AI, an intelligent meeting assistant.
Answer the user's question accurately and concisely based strictly on the provided meeting transcript and summary.

Context:
\"\"\"
{context}
\"\"\"

User Question: {question}

Instructions:
1. Base your answer ONLY on facts stated in the transcript and summary.
2. ALWAYS cite the exact spoken timestamp (e.g. '[02:15]') whenever referencing who said what.
3. If the answer cannot be found in the meeting content, clearly state: "This topic was not discussed in the meeting."
"""

        api_key = settings.GEMINI_API_KEY
        if not api_key:
            yield f"data: {json.dumps({'error': 'GEMINI_API_KEY is not configured'})}\n\n"
            return

        url = f"{GEMINI_API_BASE}/gemini-2.5-flash:streamGenerateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }

        full_answer_chunks: list[str] = []

        async with httpx.AsyncClient(timeout=90.0) as client:
            async with client.stream(
                "POST", url, json=payload, headers={"Content-Type": "application/json"}
            ) as stream:
                async for chunk in stream.aiter_lines():
                    if not chunk:
                        continue
                    clean = chunk.strip()
                    if clean.startswith("data: "):
                        clean = clean[6:]
                    if not clean or clean == "[DONE]":
                        continue
                    try:
                        data = json.loads(clean)
                        candidates = data.get("candidates", [])
                        if candidates and candidates[0].get("content", {}).get("parts", []):
                            token_text = candidates[0]["content"]["parts"][0].get("text", "")
                            if token_text:
                                full_answer_chunks.append(token_text)
                                yield f"data: {json.dumps({'token': token_text})}\n\n"
                    except Exception:
                        continue

        complete_answer = "".join(full_answer_chunks).strip()
        ref_seconds = parse_timestamp_from_text(complete_answer)

        # Save conversation in DB
        AIConversation = get_ai_conversation_model()
        now = datetime.now(UTC)
        conv_id = uuid.uuid4()
        user_uuid = uuid.UUID(str(current_user.id))

        conv_rec = AIConversation(
            id=conv_id,
            meeting_id=meeting_uuid,
            user_id=user_uuid,
            question=question,
            answer=complete_answer,
            referenced_timestamp_seconds=ref_seconds,
            created_at=now,
        )
        db.add(conv_rec)
        await db.commit()

        yield f"data: {json.dumps({'done': True, 'id': str(conv_id), 'referenced_timestamp_seconds': ref_seconds})}\n\n"

    @staticmethod
    async def get_chat_history(
        db: AsyncSession,
        meeting_id: str,
        current_user: Any,
    ) -> list[ChatMessageResponse]:
        """Retrieves chronological chat conversation history for a meeting."""
        meeting_uuid, _, _ = await QAService._get_meeting_context(db, meeting_id, current_user)
        AIConversation = get_ai_conversation_model()

        stmt = (
            select(AIConversation)
            .where(AIConversation.meeting_id == meeting_uuid)
            .order_by(asc(AIConversation.created_at))
        )
        res = await db.execute(stmt)
        rows = res.scalars().all()

        return [
            ChatMessageResponse(
                id=str(r.id),
                meeting_id=str(r.meeting_id),
                user_id=str(r.user_id),
                question=r.question,
                answer=r.answer,
                referenced_timestamp_seconds=(
                    float(r.referenced_timestamp_seconds)
                    if r.referenced_timestamp_seconds is not None
                    else None
                ),
                created_at=r.created_at,
            )
            for r in rows
        ]
