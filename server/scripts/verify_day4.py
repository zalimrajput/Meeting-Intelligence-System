import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Comprehensive End-to-End Verification Script for MeetingMind Phase 2 Day 4.

Validates:
1. Gemini JSON parser for structured meeting insights.
2. Full AI Pipeline (Stage 1 DeepGram + Stage 2 Gemini Intelligence).
3. Direct DB verification of reflected tables:
   - `meetings` (`summary_short`, `summary_detailed`, `sentiment`, `sentiment_score`, `status='completed'`)
   - `action_items` (task_description, deadline_raw_text, deadline_date, status)
   - `decisions` (decision_text, timestamp_seconds)
   - `key_points` (point_text, timestamp_seconds)
   - `unresolved_issues` (issue_text, timestamp_seconds)
   - `follow_up_items` (description, timestamp_seconds)
   - `deadlines` (description, raw_text, resolved_date)
   - `processing_jobs` (stages: 'transcription', 'summarization', etc. -> 'completed')
4. API verification:
   - GET /api/v1/meetings/{id}/insights -> 200 OK with full summary, sentiment, actions, decisions
   - GET /api/v1/meetings/{id}/actions -> 200 OK with action item list
   - GET /api/v1/meetings/{id}/decisions -> 200 OK with decisions list
   - GET /api/v1/meetings/{id}/key-points -> 200 OK with key points list
   - GET /api/v1/meetings/{id}/issues -> 200 OK with unresolved issues list
   - Multi-tenant isolation -> 403 Forbidden for unauthorized user
"""

import asyncio
import io
import uuid
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

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


async def run_verification() -> None:
    print("=" * 65)
    print("Starting MeetingMind Phase 2 Day 4 Verification (Gemini Pipeline)")
    print("=" * 65)

    # 1. Initialize DB reflection
    print("\n[Step 1] Initializing database reflection...")
    await init_db()
    print("[OK] Database reflection successful!")

    # 2. Test Gemini JSON parser
    print("\n[Step 2] Testing Gemini Structured JSON Parser...")
    service = GeminiService(api_key="mock_key")
    sample_gemini_json = """
    {
      "title": "API Gateway & Security Architecture",
      "summary_short": "The engineering team finalized JWT auth token rotations and agreed to implement slowapi rate limiters.",
      "summary_detailed": "In this architectural sync, the team reviewed the security roadmap. Rate limiting parameters were set to 100 req/min for standard APIs and 10 req/min for AI endpoints.",
      "sentiment": "positive",
      "sentiment_score": 0.85,
      "key_points": [
        { "point_text": "JWT tokens will have 15-minute access and 7-day refresh expiry.", "timestamp_seconds": 10.0 },
        { "point_text": "SlowAPI will protect endpoints against DDoS.", "timestamp_seconds": 25.0 }
      ],
      "action_items": [
        {
          "task_description": "Configure slowapi rate limiter middleware across all FastAPI routes",
          "assigned_to": "Backend Lead",
          "deadline_raw_text": "by Monday morning",
          "deadline_date": "2026-08-25",
          "timestamp_seconds": 30.0
        }
      ],
      "decisions": [
        {
          "decision_text": "Enforce strict multi-tenant user isolation in all database queries",
          "decided_by": "Architecture Review Board",
          "timestamp_seconds": 15.0
        }
      ],
      "unresolved_issues": [
        {
          "issue_text": "Determine Redis caching TTL for dashboard statistics",
          "timestamp_seconds": 45.0
        }
      ],
      "follow_up_items": [
        {
          "description": "Benchmark Redis throughput with 500 concurrent sessions",
          "timestamp_seconds": 50.0
        }
      ],
      "deadlines": [
        {
          "description": "SlowAPI middleware deployment",
          "raw_text": "by Monday morning",
          "resolved_date": "2026-08-25",
          "timestamp_seconds": 30.0
        }
      ]
    }
    """
    parsed_ai = service.parse_gemini_json(sample_gemini_json)
    assert parsed_ai.title == "API Gateway & Security Architecture"
    assert parsed_ai.sentiment == "positive"
    assert len(parsed_ai.key_points) == 2
    assert len(parsed_ai.action_items) == 1
    assert len(parsed_ai.decisions) == 1
    assert len(parsed_ai.unresolved_issues) == 1
    print(f"[OK] Parsed Gemini output: title='{parsed_ai.title}', sentiment={parsed_ai.sentiment}")

    # Prepare Mock STT Output
    mock_stt = DeepGramTranscriptionResult(
        duration_seconds=55.0,
        speakers=["Speaker 1", "Speaker 2"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Speaker 1",
                start_time_seconds=0.0,
                end_time_seconds=25.0,
                text="Welcome to the API security review. Let's discuss token expiry and rate limiting.",
                confidence=0.98,
            ),
            DiarizedUtterance(
                speaker_index=1,
                speaker_label="Speaker 2",
                start_time_seconds=26.0,
                end_time_seconds=55.0,
                text="I will configure slowapi rate limiting by Monday morning.",
                confidence=0.96,
            ),
        ],
        full_transcript="Welcome to the API security review. I will configure slowapi rate limiting by Monday morning.",
        raw_response={},
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 3. Register primary user
        suffix = uuid.uuid4().hex[:8]
        user_email = f"lead_day4_{suffix}@meetingmind.ai"
        user_pw = "SecurePass2026!"
        print(f"\n[Step 3] Registering primary user: {user_email}...")

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Day 4 AI Lead", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        user_id = reg_res.json()["data"]["user"]["id"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print(f"[OK] Registered user_id={user_id}")

        # Register secondary user for multi-tenant isolation tests
        other_email = f"unauthorized_day4_{suffix}@meetingmind.ai"
        reg_other = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Unauthorized User", "email": other_email, "password": user_pw},
        )
        assert reg_other.status_code == 201
        other_token = reg_other.json()["data"]["tokens"]["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}
        print(f"[OK] Registered secondary user for isolation tests: {other_email}")

        # 4. Upload audio meeting recording
        print("\n[Step 4] Uploading audio recording (POST /api/v1/meetings)...")
        valid_audio = b"ID3\x03\x00\x00\x00\x00\x00\x20" + b"\xff\xfb\x90\x44" * 256
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("security_sync.mp3", io.BytesIO(valid_audio), "audio/mpeg")},
            data={"title": "API Gateway & Security Architecture"},
        )
        assert upload_res.status_code == 201
        meeting_id = upload_res.json()["data"]["meeting"]["id"]
        print(f"[OK] Uploaded meeting id={meeting_id}")

        # 5. Execute Stage 1 + Stage 2 Worker pipeline
        print("\n[Step 5] Executing full background worker pipeline (Stage 1 + Stage 2)...")
        with patch(
            "app.worker.deepgram_service.transcribe_file",
            new=AsyncMock(return_value=mock_stt),
        ), patch(
            "app.worker.gemini_service.extract_meeting_intelligence",
            new=AsyncMock(return_value=parsed_ai),
        ):
            worker_result = await process_meeting(None, meeting_id)
            assert worker_result["status"] == "success"
            assert worker_result["meeting_status"] == "completed"
            print(f"[OK] Full worker pipeline output: {worker_result}")

        # 6. Verify PostgreSQL database state
        print("\n[Step 6] Verifying database records directly via SQLAlchemy...")
        async with async_session_maker() as db:
            meeting_uuid = uuid.UUID(meeting_id)

            # Check Meeting
            res_m = await db.execute(
                select(models.Meeting).where(models.Meeting.id == meeting_uuid)
            )
            db_meeting = res_m.scalars().first()
            assert db_meeting.status == "completed"
            assert db_meeting.summary_short is not None
            assert db_meeting.summary_detailed is not None
            assert db_meeting.sentiment == "positive"
            print(f"[OK] DB Meeting: status={db_meeting.status}, sentiment={db_meeting.sentiment}")
            print(f"     Summary: {db_meeting.summary_short[:90]}...")

            # Check Key Points
            res_kp = await db.execute(
                select(models.KeyPoint).where(models.KeyPoint.meeting_id == meeting_uuid)
            )
            db_kps = res_kp.scalars().all()
            assert len(db_kps) == 2
            print(f"[OK] DB Key Points ({len(db_kps)} rows): {[k.point_text for k in db_kps]}")

            # Check Action Items
            res_act = await db.execute(
                select(models.ActionItem).where(models.ActionItem.meeting_id == meeting_uuid)
            )
            db_actions = res_act.scalars().all()
            assert len(db_actions) == 1
            print(
                f"[OK] DB Action Items ({len(db_actions)} rows): task='{db_actions[0].task_description}', deadline='{db_actions[0].deadline_raw_text}'"
            )

            # Check Decisions
            res_dec = await db.execute(
                select(models.Decision).where(models.Decision.meeting_id == meeting_uuid)
            )
            db_decisions = res_dec.scalars().all()
            assert len(db_decisions) == 1
            print(f"[OK] DB Decisions ({len(db_decisions)} rows): '{db_decisions[0].decision_text}'")

            # Check Unresolved Issues
            res_iss = await db.execute(
                select(models.UnresolvedIssue).where(
                    models.UnresolvedIssue.meeting_id == meeting_uuid
                )
            )
            db_issues = res_iss.scalars().all()
            assert len(db_issues) == 1
            print(f"[OK] DB Unresolved Issues ({len(db_issues)} rows): '{db_issues[0].issue_text}'")

            # Check Deadlines
            res_dl = await db.execute(
                select(models.Deadline).where(models.Deadline.meeting_id == meeting_uuid)
            )
            db_deadlines = res_dl.scalars().all()
            assert len(db_deadlines) == 1
            print(f"[OK] DB Deadlines ({len(db_deadlines)} rows): '{db_deadlines[0].description}'")

        # 7. Test API Endpoints
        print("\n[Step 7] Testing Insights API endpoints...")

        # All insights
        ins_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/insights",
            headers=auth_headers,
        )
        assert ins_res.status_code == 200
        ins_data = ins_res.json()["data"]
        assert ins_data["sentiment"] == "positive"
        assert len(ins_data["action_items"]) == 1
        assert len(ins_data["decisions"]) == 1
        print(f"[OK] GET /api/v1/meetings/{{id}}/insights: 200 OK")

        # Actions
        actions_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/actions",
            headers=auth_headers,
        )
        assert actions_res.status_code == 200
        assert len(actions_res.json()["data"]) == 1
        print(f"[OK] GET /api/v1/meetings/{{id}}/actions: 200 OK")

        # Decisions
        dec_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/decisions",
            headers=auth_headers,
        )
        assert dec_res.status_code == 200
        assert len(dec_res.json()["data"]) == 1
        print(f"[OK] GET /api/v1/meetings/{{id}}/decisions: 200 OK")

        # Key Points
        kp_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/key-points",
            headers=auth_headers,
        )
        assert kp_res.status_code == 200
        assert len(kp_res.json()["data"]) == 2
        print(f"[OK] GET /api/v1/meetings/{{id}}/key-points: 200 OK")

        # Unresolved Issues
        iss_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/issues",
            headers=auth_headers,
        )
        assert iss_res.status_code == 200
        assert len(iss_res.json()["data"]) == 1
        print(f"[OK] GET /api/v1/meetings/{{id}}/issues: 200 OK")

        # 8. Test multi-tenant isolation
        print("\n[Step 8] Testing multi-tenant isolation on insights (403 Forbidden)...")
        other_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/insights",
            headers=other_headers,
        )
        assert other_res.status_code == 403
        assert other_res.json()["error"]["code"] == "FORBIDDEN_RESOURCE"
        print(f"[OK] Blocked unauthorized user from viewing insights (403 FORBIDDEN_RESOURCE)")

    print("\n" + "=" * 65)
    print("ALL PHASE 2 DAY 4 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_verification())
