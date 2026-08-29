"""Full End-to-End Pipeline Integration Test.

Covers:
1. User Registration & JWT Authentication
2. Media File Upload (Audio/Video)
3. Full Worker Processing Pipeline (DeepGram + Gemini Extraction)
4. Admin Queue Status & Manual Trigger APIs
5. Searchable Transcript & Insights Querying
6. Contextual Q&A AI Chat with Timestamp Grounding
7. Multi-Format Exports (Markdown, JSON, Email Digest, Plain Text)
8. Lifecycle Cleanup
"""

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
async def test_full_end_to_end_intelligence_pipeline() -> None:
    """Tests the complete end-to-end MeetingMind intelligence lifecycle."""
    await init_db()

    mock_dg = DeepGramTranscriptionResult(
        duration_seconds=95.0,
        speakers=["Alice", "Bob"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Alice",
                start_time_seconds=0.0,
                end_time_seconds=40.0,
                text="Welcome team. Today we need to finalize our Q4 product release date.",
                confidence=0.98,
            ),
            DiarizedUtterance(
                speaker_index=1,
                speaker_label="Bob",
                start_time_seconds=42.0,
                end_time_seconds=95.0,
                text="I propose we target November 15th for the global launch. I will deliver the staging build by October 30th.",
                confidence=0.97,
            ),
        ],
        full_transcript=(
            "Alice: Welcome team. Today we need to finalize our Q4 product release date. "
            "Bob: I propose we target November 15th for the global launch. I will deliver the staging build by October 30th."
        ),
        raw_response={},
    )

    mock_gemini = MeetingIntelligenceResult(
        title="Q4 Product Release Strategy",
        summary_short="The team aligned on targeting November 15th for the Q4 global launch.",
        summary_detailed=(
            "Executive meeting discussing Q4 launch readiness. Bob confirmed that the staging build "
            "will be ready by October 30th, enabling full QA before the November 15th target launch."
        ),
        sentiment="positive",
        sentiment_score=0.92,
        key_points=[
            KeyPointItem(
                point_text="Global product release target set for November 15th.",
                timestamp_seconds=42.0,
            ),
            KeyPointItem(
                point_text="Staging build due date finalized as October 30th.",
                timestamp_seconds=60.0,
            ),
        ],
        action_items=[
            ActionItemDTO(
                task_description="Deliver staging build to QA team",
                assigned_to="Bob",
                deadline_raw_text="by October 30th",
                deadline_date="2026-10-30",
                timestamp_seconds=60.0,
            )
        ],
        decisions=[
            DecisionDTO(
                decision_text="Target November 15th for Q4 global launch",
                decided_by="Alice and Bob",
                timestamp_seconds=45.0,
            )
        ],
        unresolved_issues=[
            UnresolvedIssueDTO(
                issue_text="Load test environment provisioning needs budget approval.",
                timestamp_seconds=75.0,
            )
        ],
        follow_up_items=[
            FollowUpDTO(
                description="Schedule follow-up review with QA lead.",
                timestamp_seconds=80.0,
            )
        ],
        deadlines=[
            DeadlineDTO(
                description="Staging build delivery",
                raw_text="by October 30th",
                resolved_date="2026-10-30",
                timestamp_seconds=60.0,
            )
        ],
        raw_response={},
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Register User & Obtain JWT Token
        suffix = uuid.uuid4().hex[:8]
        user_email = f"e2e_lead_{suffix}@meetingmind.ai"
        user_pw = "Enterprise2026!Pass"

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "E2E Lead Engineer", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. Upload Meeting Recording
        audio_content = b"ID3\x03\x00\x00\x00\x00\x00\x20" + (b"\xff\xfb\x90\x44" * 300)
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("q4_release_planning.mp3", io.BytesIO(audio_content), "audio/mpeg")},
            data={"title": "Q4 Product Release Strategy"},
        )
        assert upload_res.status_code == 201
        meeting_data = upload_res.json()["data"]["meeting"]
        meeting_id = meeting_data["id"]
        assert meeting_data["title"] == "Q4 Product Release Strategy"
        assert meeting_data["status"] == "uploaded"

        # 3. Test Admin Queue Status API
        queue_status_res = await client.get(
            "/api/v1/admin/queue/status",
            headers=auth_headers,
        )
        assert queue_status_res.status_code == 200
        qs_data = queue_status_res.json()["data"]
        assert "job_counts" in qs_data
        assert "worker_status" in qs_data

        # 4. Process Meeting via Background Worker (mocked AI models)
        with patch(
            "app.worker.deepgram_service.transcribe_file",
            new=AsyncMock(return_value=mock_dg),
        ), patch(
            "app.worker.gemini_service.extract_meeting_intelligence",
            new=AsyncMock(return_value=mock_gemini),
        ):
            worker_res = await process_meeting(None, meeting_id)
            assert worker_res["status"] == "success"
            assert worker_res["meeting_status"] == "completed"
            assert worker_res["action_items_count"] == 1
            assert worker_res["decisions_count"] == 1

        # 5. Verify Meeting Details & Intelligence Ingestion
        m_details_res = await client.get(
            f"/api/v1/meetings/{meeting_id}",
            headers=auth_headers,
        )
        assert m_details_res.status_code == 200
        m_info = m_details_res.json()["data"]
        assert m_info["status"] == "completed"
        assert m_info["sentiment"] == "positive"
        assert "November 15th" in m_info["summary_short"]

        # 6. Verify Transcripts API
        tx_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/transcript",
            headers=auth_headers,
        )
        assert tx_res.status_code == 200
        tx_segments = tx_res.json()["data"]
        assert len(tx_segments) == 2
        assert tx_segments[0]["speaker_label"] == "Alice"
        assert tx_segments[1]["speaker_label"] == "Bob"

        # 7. Verify Insights Endpoints (Actions, Decisions, All Insights)
        insights_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/insights",
            headers=auth_headers,
        )
        assert insights_res.status_code == 200
        ins_data = insights_res.json()["data"]
        assert len(ins_data["action_items"]) == 1
        assert ins_data["action_items"][0]["task_description"] == "Deliver staging build to QA team"
        assert len(ins_data["decisions"]) == 1
        assert ins_data["decisions"][0]["decision_text"] == "Target November 15th for Q4 global launch"
        assert len(ins_data["unresolved_issues"]) == 1

        # 8. Test Ask AI Chat with Citations
        mock_gemini_chat_resp = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    "The launch date is finalized for November 15th around the 42-second mark [00:42]. "
                                    "Bob will deliver the staging build by October 30th [01:00]."
                                )
                            }
                        ]
                    }
                }
            ]
        }
        with patch(
            "app.modules.qa.service.QAService._call_gemini_api",
            new=AsyncMock(return_value=mock_gemini_chat_resp),
        ):
            chat_res = await client.post(
                f"/api/v1/meetings/{meeting_id}/chat",
                headers=auth_headers,
                json={"question": "When is the launch date and who is delivering staging?"},
            )
            assert chat_res.status_code == 200
            chat_data = chat_res.json()["data"]
            assert "November 15th" in chat_data["answer"]
            assert chat_data["referenced_timestamp_seconds"] == 42.0

            # Verify Chat History API
            history_res = await client.get(
                f"/api/v1/meetings/{meeting_id}/chat",
                headers=auth_headers,
            )
            assert history_res.status_code == 200
            history_list = history_res.json()["data"]
            assert len(history_list) >= 1
            assert history_list[0]["question"] == "When is the launch date and who is delivering staging?"
            assert "November 15th" in history_list[0]["answer"]

        # 9. Test Multi-Format Exports
        # Markdown
        md_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/export?format=markdown",
            headers=auth_headers,
        )
        assert md_res.status_code == 200
        assert "Q4 Product Release Strategy" in md_res.text
        assert "November 15th" in md_res.text

        # JSON
        json_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/export?format=json",
            headers=auth_headers,
        )
        assert json_res.status_code == 200
        exported_json = json.loads(json_res.text)
        assert exported_json["title"] == "Q4 Product Release Strategy"
        assert len(exported_json["action_items"]) == 1

        # Email
        email_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/export?format=email",
            headers=auth_headers,
        )
        assert email_res.status_code == 200
        assert "EXECUTIVE SUMMARY" in email_res.text

        # Text
        text_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/export?format=text",
            headers=auth_headers,
        )
        assert text_res.status_code == 200
        assert "Q4 Product Release Strategy" in text_res.text

        # 10. Test Admin Manual Trigger API
        trigger_res = await client.post(
            f"/api/v1/admin/queue/trigger/{meeting_id}",
            headers=auth_headers,
        )
        assert trigger_res.status_code == 200
        assert trigger_res.json()["data"]["status"] == "uploaded"

        # 11. Cleanup: Hard Delete Meeting
        del_res = await client.delete(
            f"/api/v1/meetings/{meeting_id}",
            headers=auth_headers,
        )
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True
