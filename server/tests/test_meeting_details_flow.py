"""Unit and integration tests for Phase 3 Day 5: Meeting Details, Media Playback & Action Mutations."""

import io
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import async_session_maker, init_db, models
from app.main import app
from app.services.deepgram_service import (
    DeepGramTranscriptionResult,
    DiarizedUtterance,
)
from app.services.gemini_service import (
    ActionItemDTO,
    DecisionDTO,
    DeadlineDTO,
    FollowUpDTO,
    KeyPointItem,
    MeetingIntelligenceResult,
    UnresolvedIssueDTO,
)
from app.worker import process_meeting


@pytest.mark.asyncio
async def test_meeting_details_media_and_actions_flow() -> None:
    """Tests Media streaming (with range requests), action item mutations, and searchable transcripts."""
    await init_db()

    mock_dg = DeepGramTranscriptionResult(
        duration_seconds=30.0,
        speakers=["Speaker 1"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Speaker 1",
                start_time_seconds=0.0,
                end_time_seconds=15.0,
                text="Welcome to the dashboard synchronization meeting.",
                confidence=0.98,
            ),
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Speaker 1",
                start_time_seconds=16.0,
                end_time_seconds=30.0,
                text="Please complete the frontend integration tests before tomorrow.",
                confidence=0.95,
            ),
        ],
        full_transcript="Welcome to the dashboard synchronization meeting. Please complete the frontend integration tests before tomorrow.",
        raw_response={},
    )

    mock_gemini = MeetingIntelligenceResult(
        title="Dashboard Sync",
        summary_short="Brief meeting on dashboard sync and integration tests.",
        summary_detailed="The team reviewed media playback and action item tracking features.",
        sentiment="positive",
        sentiment_score=0.9,
        key_points=[
            KeyPointItem(point_text="Integration tests required.", timestamp_seconds=16.0),
        ],
        action_items=[
            ActionItemDTO(
                task_description="Complete frontend integration tests",
                assigned_to="Speaker 1",
                deadline_raw_text="before tomorrow",
                deadline_date="2026-08-23",
                timestamp_seconds=18.0,
            )
        ],
        decisions=[
            DecisionDTO(
                decision_text="Enable media streaming endpoint",
                timestamp_seconds=5.0,
            )
        ],
        unresolved_issues=[],
        follow_up_items=[],
        deadlines=[],
        raw_response={},
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Register user
        suffix = uuid.uuid4().hex[:8]
        user_email = f"details_lead_{suffix}@meetingmind.ai"
        user_pw = "Password123!Safe"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Details Lead", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Upload audio meeting
        dummy_audio_bytes = b"ID3\x03\x00\x00\x00\x00\x00\x20" + (b"\xff\xfb\x90\x44" * 256)
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("sync.mp3", io.BytesIO(dummy_audio_bytes), "audio/mpeg")},
            data={"title": "Dashboard Sync"},
        )
        assert upload_res.status_code == 201
        meeting_id = upload_res.json()["data"]["meeting"]["id"]

        # 3. Process meeting
        with patch(
            "app.worker.deepgram_service.transcribe_file",
            new=AsyncMock(return_value=mock_dg),
        ), patch(
            "app.worker.gemini_service.extract_meeting_intelligence",
            new=AsyncMock(return_value=mock_gemini),
        ):
            worker_res = await process_meeting(None, meeting_id)
            assert worker_res["status"] == "success"

        # 4. Test Media Streaming (Full 200 OK & Range 206 Partial Content)
        full_media_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/media",
            headers=auth_headers,
        )
        assert full_media_res.status_code == 200
        assert full_media_res.headers.get("accept-ranges") == "bytes"
        assert len(full_media_res.content) == len(dummy_audio_bytes)

        range_media_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/media",
            headers={**auth_headers, "Range": "bytes=0-99"},
        )
        assert range_media_res.status_code == 206
        assert range_media_res.headers.get("content-range").startswith("bytes 0-99/")
        assert len(range_media_res.content) == 100

        # 5. Test Searchable Transcripts (GET /transcript?search=integration)
        search_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/transcript?search=integration",
            headers=auth_headers,
        )
        assert search_res.status_code == 200
        search_segments = search_res.json()["data"]
        assert len(search_segments) == 1
        assert "integration" in search_segments[0]["text"]

        no_match_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/transcript?search=nonexistent_xyz",
            headers=auth_headers,
        )
        assert no_match_res.status_code == 200
        assert len(no_match_res.json()["data"]) == 0

        # 6. Test Action Items Mutation
        # 6a. Get existing action item
        actions_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/actions",
            headers=auth_headers,
        )
        assert actions_res.status_code == 200
        actions = actions_res.json()["data"]
        assert len(actions) == 1
        action_id = actions[0]["id"]
        assert actions[0]["status"] == "pending"

        # 6b. Update status to 'completed' via PATCH
        patch_res = await client.patch(
            f"/api/v1/meetings/{meeting_id}/actions/{action_id}",
            headers=auth_headers,
            json={"status": "completed", "deadline_date": "2026-08-25"},
        )
        assert patch_res.status_code == 200
        updated_act = patch_res.json()["data"]
        assert updated_act["status"] == "completed"
        assert updated_act["deadline_date"] == "2026-08-25"

        # 6c. Create manual action item via POST
        create_res = await client.post(
            f"/api/v1/meetings/{meeting_id}/actions",
            headers=auth_headers,
            json={
                "task_description": "Deploy staging server build",
                "assigned_to": "DevOps",
                "status": "in_progress",
            },
        )
        assert create_res.status_code == 201
        created_action_id = create_res.json()["data"]["id"]

        # Verify count is now 2
        actions_res2 = await client.get(
            f"/api/v1/meetings/{meeting_id}/actions",
            headers=auth_headers,
        )
        assert len(actions_res2.json()["data"]) == 2

        # 6d. Delete manual action item via DELETE
        del_res = await client.delete(
            f"/api/v1/meetings/{meeting_id}/actions/{created_action_id}",
            headers=auth_headers,
        )
        assert del_res.status_code == 200
        assert del_res.json()["data"]["deleted"] is True

        # Verify count is 1 again
        actions_res3 = await client.get(
            f"/api/v1/meetings/{meeting_id}/actions",
            headers=auth_headers,
        )
        assert len(actions_res3.json()["data"]) == 1
