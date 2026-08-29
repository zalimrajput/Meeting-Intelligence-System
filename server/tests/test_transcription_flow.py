"""Unit and integration tests for Phase 2 Day 3: DeepGram Transcription & Diarization."""

import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import async_session_maker, init_db, models
from app.main import app
from app.services.deepgram_service import (
    DeepGramService,
    DeepGramTranscriptionResult,
    DiarizedUtterance,
)
from app.services.gemini_service import MeetingIntelligenceResult
from app.worker import process_meeting


def test_deepgram_response_parsing() -> None:
    """Tests parsing DeepGram JSON response into structured utterances and speakers."""
    service = DeepGramService(api_key="test_key")

    mock_response = {
        "metadata": {"duration": 15.5},
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "Hello everyone. Welcome to the meeting. Let's begin the review."
                        }
                    ]
                }
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "start": 0.0,
                    "end": 4.2,
                    "transcript": "Hello everyone. Welcome to the meeting.",
                    "confidence": 0.98,
                },
                {
                    "speaker": 1,
                    "start": 4.5,
                    "end": 9.1,
                    "transcript": "Thanks Alice. Let's review the quarterly roadmap.",
                    "confidence": 0.95,
                },
                {
                    "speaker": 0,
                    "start": 9.5,
                    "end": 14.8,
                    "transcript": "Sure, I'll share my screen right now.",
                    "confidence": 0.99,
                },
            ],
        },
    }

    result = service.parse_response(mock_response)

    assert result.duration_seconds == 15.5
    assert len(result.speakers) == 2
    assert result.speakers == ["Speaker 1", "Speaker 2"]
    assert len(result.utterances) == 3

    assert result.utterances[0].speaker_label == "Speaker 1"
    assert result.utterances[0].speaker_index == 0
    assert result.utterances[0].start_time_seconds == 0.0
    assert result.utterances[0].end_time_seconds == 4.2
    assert result.utterances[0].text == "Hello everyone. Welcome to the meeting."
    assert result.utterances[0].confidence == 0.98

    assert result.utterances[1].speaker_label == "Speaker 2"
    assert result.utterances[1].speaker_index == 1
    assert result.utterances[1].text == "Thanks Alice. Let's review the quarterly roadmap."


@pytest.mark.asyncio
async def test_end_to_end_transcription_pipeline() -> None:
    """Tests full Stage 1 pipeline: upload -> worker transcription -> DB persistence -> API retrieval."""
    await init_db()

    mock_result = DeepGramTranscriptionResult(
        duration_seconds=32.4,
        speakers=["Speaker 1", "Speaker 2"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Speaker 1",
                start_time_seconds=0.0,
                end_time_seconds=12.5,
                text="Welcome team to the sprint planning session.",
                confidence=0.97,
            ),
            DiarizedUtterance(
                speaker_index=1,
                speaker_label="Speaker 2",
                start_time_seconds=13.0,
                end_time_seconds=32.4,
                text="I have prepared the backend migration tasks for review.",
                confidence=0.96,
            ),
        ],
        full_transcript="Welcome team to the sprint planning session. I have prepared the backend migration tasks for review.",
        raw_response={},
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Register test user
        suffix = uuid.uuid4().hex[:8]
        user_email = f"transcribe_tester_{suffix}@meetingmind.ai"
        user_pw = "Password123!Safe"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Transcription Tester", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        user_id = reg_res.json()["data"]["user"]["id"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Upload valid audio recording
        valid_audio = b"ID3\x03\x00\x00\x00\x00\x00\x10" + b"\xff\xfb\x90\x44" * 128
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("sprint_planning.mp3", io.BytesIO(valid_audio), "audio/mpeg")},
            data={"title": "Sprint 42 Planning"},
        )
        assert upload_res.status_code == 201
        meeting_id = upload_res.json()["data"]["meeting"]["id"]

        # 3. Execute worker process_meeting with mocked DeepGram and Gemini calls
        mock_ai_summary = MeetingIntelligenceResult(
            title="Sprint 42 Planning",
            summary_short="Sprint planning sync for roadmap milestones.",
            summary_detailed="Detailed roadmap review for sprint 42.",
            sentiment="positive",
            sentiment_score=0.85,
            key_points=[],
            action_items=[],
            decisions=[],
            unresolved_issues=[],
            follow_up_items=[],
            deadlines=[],
            raw_response={},
        )
        with patch(
            "app.worker.deepgram_service.transcribe_file",
            new=AsyncMock(return_value=mock_result),
        ), patch(
            "app.worker.gemini_service.extract_meeting_intelligence",
            new=AsyncMock(return_value=mock_ai_summary),
        ):
            worker_res = await process_meeting(None, meeting_id)
            assert worker_res["status"] == "success"
            assert worker_res["meeting_id"] == meeting_id
            assert worker_res["speakers_count"] == 2
            assert worker_res["segments_count"] == 2

        # 4. Verify API GET /api/v1/meetings/{id}/transcript
        transcript_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/transcript",
            headers=auth_headers,
        )
        assert transcript_res.status_code == 200
        t_data = transcript_res.json()
        assert t_data["success"] is True
        segments = t_data["data"]
        assert len(segments) == 2

        seg0 = segments[0]
        assert seg0["segment_index"] == 0
        assert seg0["speaker_label"] == "Speaker 1"
        assert seg0["text"] == "Welcome team to the sprint planning session."
        assert seg0["start_time_seconds"] == 0.0
        assert seg0["end_time_seconds"] == 12.5

        seg1 = segments[1]
        assert seg1["segment_index"] == 1
        assert seg1["speaker_label"] == "Speaker 2"
        assert seg1["text"] == "I have prepared the backend migration tasks for review."

        # 5. Check meeting status updated to 'completed'
        meeting_res = await client.get(
            f"/api/v1/meetings/{meeting_id}",
            headers=auth_headers,
        )
        assert meeting_res.status_code == 200
        m_info = meeting_res.json()["data"]
        assert m_info["status"] in ["completed", "analyzing"]
        assert m_info["duration_seconds"] == 32


