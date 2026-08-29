"""Unit and integration tests for Phase 2 Day 4: Gemini Intelligence Extraction."""

import io
import uuid
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
    GeminiService,
    KeyPointItem,
    MeetingIntelligenceResult,
    UnresolvedIssueDTO,
)
from app.worker import process_meeting


def test_gemini_json_parsing() -> None:
    """Tests parsing structured JSON output from Gemini."""
    service = GeminiService(api_key="test_key")

    mock_gemini_json = """
    {
      "title": "Q3 Cloud Migration Strategy",
      "summary_short": "The team agreed to migrate backend services to AWS by next month. Alice will lead infrastructure.",
      "summary_detailed": "During the meeting, the engineering team reviewed architecture choices and selected PostgreSQL on RDS. Migration timelines and security protocols were finalized.",
      "sentiment": "positive",
      "sentiment_score": 0.85,
      "key_points": [
        { "point_text": "PostgreSQL was selected over DynamoDB.", "timestamp_seconds": 12.0 },
        { "point_text": "Target cutover date set for end of August.", "timestamp_seconds": 45.5 }
      ],
      "action_items": [
        {
          "task_description": "Provision staging VPC and database clusters",
          "assigned_to": "Alice",
          "deadline_raw_text": "by next Friday",
          "deadline_date": "2026-08-28",
          "timestamp_seconds": 25.0
        }
      ],
      "decisions": [
        {
          "decision_text": "Use AWS RDS Multi-AZ for high availability.",
          "decided_by": "Architecture Team",
          "timestamp_seconds": 18.0
        }
      ],
      "unresolved_issues": [
        {
          "issue_text": "Backup retention policy needs compliance approval.",
          "timestamp_seconds": 55.0
        }
      ],
      "follow_up_items": [
        {
          "description": "Schedule security review with compliance team.",
          "timestamp_seconds": 60.0
        }
      ],
      "deadlines": [
        {
          "description": "VPC provisioning",
          "raw_text": "by next Friday",
          "resolved_date": "2026-08-28",
          "timestamp_seconds": 25.0
        }
      ]
    }
    """

    result = service.parse_gemini_json(mock_gemini_json)

    assert result.title == "Q3 Cloud Migration Strategy"
    assert result.sentiment == "positive"
    assert result.sentiment_score == 0.85
    assert len(result.key_points) == 2
    assert len(result.action_items) == 1
    assert result.action_items[0].assigned_to == "Alice"
    assert result.action_items[0].deadline_date == "2026-08-28"
    assert len(result.decisions) == 1
    assert len(result.unresolved_issues) == 1


@pytest.mark.asyncio
async def test_end_to_end_insights_pipeline() -> None:
    """Tests Stage 1 + Stage 2 AI Pipeline: Upload -> DeepGram -> Gemini -> DB -> Insights APIs."""
    await init_db()

    mock_dg_result = DeepGramTranscriptionResult(
        duration_seconds=45.0,
        speakers=["Speaker 1", "Speaker 2"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Speaker 1",
                start_time_seconds=0.0,
                end_time_seconds=20.0,
                text="Welcome everyone. We need to decide on our cloud provider and set action items.",
                confidence=0.98,
            ),
            DiarizedUtterance(
                speaker_index=1,
                speaker_label="Speaker 2",
                start_time_seconds=21.0,
                end_time_seconds=45.0,
                text="I suggest AWS with Supabase. I will complete the setup by Friday.",
                confidence=0.96,
            ),
        ],
        full_transcript="Welcome everyone. We need to decide on our cloud provider. I suggest AWS with Supabase. I will complete the setup by Friday.",
        raw_response={},
    )

    mock_gemini_result = MeetingIntelligenceResult(
        title="Cloud Architecture & Setup Sync",
        summary_short="The team evaluated cloud providers and chose AWS with Supabase for data persistence.",
        summary_detailed="Comprehensive review of cloud architectures. Speaker 2 volunteered to complete initial provisioning by Friday.",
        sentiment="positive",
        sentiment_score=0.8,
        key_points=[
            KeyPointItem(point_text="Selected AWS and Supabase.", timestamp_seconds=21.0),
        ],
        action_items=[
            ActionItemDTO(
                task_description="Complete cloud provisioning and database setup",
                assigned_to="Speaker 2",
                deadline_raw_text="by Friday",
                deadline_date="2026-08-28",
                timestamp_seconds=30.0,
            ),
        ],
        decisions=[
            DecisionDTO(
                decision_text="Adopt Supabase PostgreSQL for persistent database storage",
                decided_by="Speaker 2",
                timestamp_seconds=22.0,
            ),
        ],
        unresolved_issues=[
            UnresolvedIssueDTO(
                issue_text="Decide whether to use Redis cluster or single node.",
                timestamp_seconds=40.0,
            ),
        ],
        follow_up_items=[
            FollowUpDTO(description="Check Redis sizing requirements.", timestamp_seconds=42.0),
        ],
        deadlines=[
            DeadlineDTO(
                description="Cloud provisioning",
                raw_text="by Friday",
                resolved_date="2026-08-28",
                timestamp_seconds=30.0,
            ),
        ],
        raw_response={},
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Register user
        suffix = uuid.uuid4().hex[:8]
        user_email = f"insights_user_{suffix}@meetingmind.ai"
        user_pw = "Password123!Safe"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Insights Tester", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Upload meeting
        valid_audio = b"ID3\x03\x00\x00\x00\x00\x00\x10" + b"\xff\xfb\x90\x44" * 128
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("infra_sync.mp3", io.BytesIO(valid_audio), "audio/mpeg")},
            data={"title": "Cloud Infrastructure Strategy"},
        )
        assert upload_res.status_code == 201
        meeting_id = upload_res.json()["data"]["meeting"]["id"]

        # 3. Process meeting with Stage 1 + Stage 2 mocked
        with patch(
            "app.worker.deepgram_service.transcribe_file",
            new=AsyncMock(return_value=mock_dg_result),
        ), patch(
            "app.worker.gemini_service.extract_meeting_intelligence",
            new=AsyncMock(return_value=mock_gemini_result),
        ):
            worker_res = await process_meeting(None, meeting_id)
            assert worker_res["status"] == "success"
            assert worker_res["meeting_status"] == "completed"
            assert worker_res["action_items_count"] == 1
            assert worker_res["decisions_count"] == 1

        # 4. Verify GET /api/v1/meetings/{id}/insights
        all_insights_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/insights",
            headers=auth_headers,
        )
        assert all_insights_res.status_code == 200
        ins_data = all_insights_res.json()["data"]
        assert ins_data["sentiment"] == "positive"
        assert ins_data["sentiment_score"] == 0.8
        assert len(ins_data["action_items"]) == 1
        assert ins_data["action_items"][0]["task_description"] == "Complete cloud provisioning and database setup"
        assert len(ins_data["decisions"]) == 1
        assert len(ins_data["key_points"]) == 1
        assert len(ins_data["unresolved_issues"]) == 1

        # 5. Verify GET /api/v1/meetings/{id}/actions
        act_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/actions",
            headers=auth_headers,
        )
        assert act_res.status_code == 200
        actions = act_res.json()["data"]
        assert len(actions) == 1
        assert actions[0]["task_description"] == "Complete cloud provisioning and database setup"

        # 6. Verify GET /api/v1/meetings/{id}/decisions
        dec_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/decisions",
            headers=auth_headers,
        )
        assert dec_res.status_code == 200
        decisions = dec_res.json()["data"]
        assert len(decisions) == 1
        assert decisions[0]["decision_text"] == "Adopt Supabase PostgreSQL for persistent database storage"

        # 7. Verify meeting status is completed in GET /api/v1/meetings/{id}
        m_res = await client.get(
            f"/api/v1/meetings/{meeting_id}",
            headers=auth_headers,
        )
        assert m_res.status_code == 200
        m_data = m_res.json()["data"]
        assert m_data["status"] == "completed"
        assert m_data["summary_short"] is not None
