"""Unit and integration tests for Phase 3 Day 6: Meeting Q&A Chat & Dashboard Intelligence."""

import io
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_meeting_qa_and_dashboard_flow() -> None:
    """Tests Q&A chat with timestamp citations, conversation history, dashboard metrics, and global search."""
    await init_db()

    mock_dg = DeepGramTranscriptionResult(
        duration_seconds=60.0,
        speakers=["Speaker 1", "Speaker 2"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Speaker 1",
                start_time_seconds=0.0,
                end_time_seconds=30.0,
                text="Let us discuss the Kubernetes deployment deadline.",
                confidence=0.98,
            ),
            DiarizedUtterance(
                speaker_index=1,
                speaker_label="Speaker 2",
                start_time_seconds=31.0,
                end_time_seconds=60.0,
                text="The Kubernetes cluster will be deployed on EKS by next Friday.",
                confidence=0.95,
            ),
        ],
        full_transcript="Let us discuss the Kubernetes deployment deadline. The Kubernetes cluster will be deployed on EKS by next Friday.",
        raw_response={},
    )

    mock_ai = MeetingIntelligenceResult(
        title="Kubernetes Infrastructure Sync",
        summary_short="The team reviewed the Kubernetes deployment schedule and chose AWS EKS.",
        summary_detailed="Comprehensive review of Kubernetes cluster provisioning on AWS EKS.",
        sentiment="positive",
        sentiment_score=0.85,
        key_points=[
            KeyPointItem(point_text="EKS chosen as orchestrator.", timestamp_seconds=31.0)
        ],
        action_items=[
            ActionItemDTO(
                task_description="Deploy Kubernetes EKS clusters",
                assigned_to="Speaker 2",
                deadline_raw_text="by next Friday",
                deadline_date="2026-08-28",
                timestamp_seconds=35.0,
            )
        ],
        decisions=[
            DecisionDTO(
                decision_text="Use AWS EKS for container orchestration",
                timestamp_seconds=32.0,
            )
        ],
        unresolved_issues=[],
        follow_up_items=[],
        deadlines=[
            DeadlineDTO(
                description="EKS Cluster deployment",
                raw_text="by next Friday",
                resolved_date="2026-08-28",
                timestamp_seconds=35.0,
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
        user_email = f"qa_lead_{suffix}@meetingmind.ai"
        user_pw = "Password123!Safe"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "QA Lead", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Upload meeting
        audio_data = b"ID3\x03\x00\x00\x00\x00\x00\x20" + (b"\xff\xfb\x90\x44" * 256)
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("k8s.mp3", io.BytesIO(audio_data), "audio/mpeg")},
            data={"title": "Kubernetes Infrastructure Sync"},
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

        # 4. Test Meeting Q&A Chat (POST /meetings/{id}/chat)
        mock_gemini_qa_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "The Kubernetes cluster will be deployed on AWS EKS by next Friday as confirmed by Speaker 2 at [00:31]."
                            }
                        ]
                    }
                }
            ]
        }

        with patch("app.modules.qa.service.QAService._call_gemini_api", new=AsyncMock(return_value=mock_gemini_qa_response)):
            chat_res = await client.post(
                f"/api/v1/meetings/{meeting_id}/chat",
                headers=auth_headers,
                json={"question": "When will Kubernetes be deployed?"},
            )
            assert chat_res.status_code == 200
            chat_data = chat_res.json()["data"]
            assert "AWS EKS" in chat_data["answer"]
            assert chat_data["referenced_timestamp_seconds"] == 31.0



        # 5. Test Chat History (GET /meetings/{id}/chat)
        history_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/chat",
            headers=auth_headers,
        )
        assert history_res.status_code == 200
        history = history_res.json()["data"]
        assert len(history) == 1
        assert history[0]["question"] == "When will Kubernetes be deployed?"

        # 6. Test Dashboard Stats (GET /dashboard/stats)
        stats_res = await client.get(
            "/api/v1/dashboard/stats",
            headers=auth_headers,
        )
        assert stats_res.status_code == 200
        stats = stats_res.json()["data"]
        assert stats["total_meetings"] >= 1
        assert stats["total_duration_seconds"] >= 60
        assert stats["action_items"]["total"] >= 1
        assert stats["total_decisions"] >= 1
        assert stats["sentiment"]["positive"] >= 1

        # 7. Test Upcoming Deadlines (GET /dashboard/deadlines)
        deadlines_res = await client.get(
            "/api/v1/dashboard/deadlines",
            headers=auth_headers,
        )
        assert deadlines_res.status_code == 200
        deadlines = deadlines_res.json()["data"]
        assert len(deadlines) >= 1
        assert deadlines[0]["meeting_title"] == "Kubernetes Infrastructure Sync"

        # 8. Test Recent Decisions (GET /dashboard/decisions)
        decisions_res = await client.get(
            "/api/v1/dashboard/decisions",
            headers=auth_headers,
        )
        assert decisions_res.status_code == 200
        decisions = decisions_res.json()["data"]
        assert len(decisions) >= 1
        assert "AWS EKS" in decisions[0]["decision_text"]

        # 9. Test Recent Meetings (GET /dashboard/recent-meetings)
        recent_m_res = await client.get(
            "/api/v1/dashboard/recent-meetings",
            headers=auth_headers,
        )
        assert recent_m_res.status_code == 200
        recent_meetings = recent_m_res.json()["data"]
        assert len(recent_meetings) >= 1
        assert recent_meetings[0]["action_items_count"] >= 1

        # 10. Test Global Search (GET /search?q=Kubernetes)
        search_res = await client.get(
            "/api/v1/search?q=Kubernetes",
            headers=auth_headers,
        )
        assert search_res.status_code == 200
        search_result = search_res.json()["data"]
        assert search_result["total_matches"] >= 1
        assert len(search_result["meetings"]) >= 1
        assert len(search_result["transcripts"]) >= 1
