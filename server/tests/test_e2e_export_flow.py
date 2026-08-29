"""Unit and integration tests for Phase 4: Meeting Export Utilities (Markdown, JSON, Text, Email Digest)."""

import io
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import init_db
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
async def test_meeting_export_flow() -> None:
    """Tests exporting meeting intelligence to Markdown, JSON, Text, and Email formats."""
    await init_db()

    mock_dg = DeepGramTranscriptionResult(
        duration_seconds=120.0,
        speakers=["Speaker 1", "Speaker 2"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Speaker 1",
                start_time_seconds=0.0,
                end_time_seconds=60.0,
                text="Welcome to the product launch roadmap review.",
                confidence=0.98,
            ),
            DiarizedUtterance(
                speaker_index=1,
                speaker_label="Speaker 2",
                start_time_seconds=61.0,
                end_time_seconds=120.0,
                text="We will launch on ProductHunt next Tuesday.",
                confidence=0.97,
            ),
        ],
        full_transcript="Welcome to the product launch roadmap review. We will launch on ProductHunt next Tuesday.",
        raw_response={},
    )

    mock_ai = MeetingIntelligenceResult(
        title="Product Launch Roadmap Review",
        summary_short="The team finalized the ProductHunt launch date for next Tuesday.",
        summary_detailed="Detailed discussion of marketing collateral and launch timing on ProductHunt.",
        sentiment="positive",
        sentiment_score=0.92,
        key_points=[
            KeyPointItem(point_text="ProductHunt launch set for Tuesday.", timestamp_seconds=61.0)
        ],
        action_items=[
            ActionItemDTO(
                task_description="Prepare ProductHunt assets & screenshots",
                assigned_to="Speaker 2",
                deadline_raw_text="by Monday",
                deadline_date="2026-08-25",
                timestamp_seconds=65.0,
            )
        ],
        decisions=[
            DecisionDTO(
                decision_text="Launch officially on ProductHunt on Tuesday",
                timestamp_seconds=62.0,
            )
        ],
        unresolved_issues=[],
        follow_up_items=[],
        deadlines=[
            DeadlineDTO(
                description="Asset preparation",
                raw_text="by Monday",
                resolved_date="2026-08-25",
                timestamp_seconds=65.0,
            )
        ],
        raw_response={},
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Register User
        suffix = uuid.uuid4().hex[:8]
        user_email = f"export_user_{suffix}@meetingmind.ai"
        user_pw = "StrongPass2026!"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Export Tester", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Upload meeting
        audio_data = b"ID3\x03\x00\x00\x00\x00\x00\x20" + (b"\xff\xfb\x90\x44" * 256)
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("launch_roadmap.mp3", io.BytesIO(audio_data), "audio/mpeg")},
            data={"title": "Product Launch Roadmap Review"},
        )
        assert upload_res.status_code == 201
        meeting_id = upload_res.json()["data"]["meeting"]["id"]

        # 3. Process meeting
        with patch(
            "app.worker.deepgram_service.transcribe_file",
            new=AsyncMock(return_value=mock_dg),
        ), patch(
            "app.worker.gemini_service.extract_meeting_intelligence",
            new=AsyncMock(return_value=mock_ai),
        ):
            worker_res = await process_meeting(None, meeting_id)
            assert worker_res["status"] == "success"

        # 4. Test Markdown Export (GET /meetings/{id}/export?format=markdown)
        md_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/export?format=markdown",
            headers=auth_headers,
        )
        assert md_res.status_code == 200
        assert "text/markdown" in md_res.headers["content-type"]
        assert "Product Launch Roadmap Review" in md_res.text
        assert "Executive Summary" in md_res.text
        assert "Action Items" in md_res.text
        assert "Prepare ProductHunt assets" in md_res.text

        # 5. Test JSON Export (GET /meetings/{id}/export?format=json)
        json_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/export?format=json",
            headers=auth_headers,
        )
        assert json_res.status_code == 200
        assert "application/json" in json_res.headers["content-type"]
        parsed = json.loads(json_res.text)
        assert parsed["title"] == "Product Launch Roadmap Review"
        assert len(parsed["action_items"]) == 1
        assert len(parsed["decisions"]) == 1
        assert len(parsed["transcript_segments"]) == 2

        # 6. Test Email Digest Export (GET /meetings/{id}/export?format=email)
        email_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/export?format=email",
            headers=auth_headers,
        )
        assert email_res.status_code == 200
        assert "Subject: [Executive Briefing]" in email_res.text
        assert "EXECUTIVE SUMMARY" in email_res.text
        assert "ACTION ITEMS & DELIVERABLES" in email_res.text

        # 7. Test Plain Text Export (GET /meetings/{id}/export?format=text)
        txt_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/export?format=text",
            headers=auth_headers,
        )
        assert txt_res.status_code == 200
        assert "Product Launch Roadmap Review" in txt_res.text
