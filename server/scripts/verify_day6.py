import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Comprehensive End-to-End Verification Script for MeetingMind Phase 3 Day 6.

Validates:
1. Meeting Q&A Chat (RAG with transcript context + timestamp citations).
2. Referenced timestamp parsing (seconds extracted from [MM:SS]).
3. Chronological conversation history persistence in `ai_conversations`.
4. Dashboard Analytics & Stats Aggregation:
   - `GET /api/v1/dashboard/stats`
   - `GET /api/v1/dashboard/deadlines`
   - `GET /api/v1/dashboard/decisions`
   - `GET /api/v1/dashboard/recent-meetings`
5. Global Cross-Meeting Search (`GET /api/v1/search?q=...`).
6. Multi-Tenant Authorization Security Checks on Q&A and Dashboard data.
"""

import asyncio
import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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
    KeyPointItem,
    MeetingIntelligenceResult,
)
from app.worker import process_meeting


async def run_verification() -> None:
    print("=" * 65)
    print("Starting MeetingMind Phase 3 Day 6 Verification (Q&A & Dashboard)")
    print("=" * 65)

    print("\n[Step 1] Initializing database reflection...")
    await init_db()
    print("[OK] Database reflection successful!")

    mock_stt = DeepGramTranscriptionResult(
        duration_seconds=90.0,
        speakers=["Alice", "Bob"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Alice",
                start_time_seconds=0.0,
                end_time_seconds=45.0,
                text="Welcome everyone. We must finalize the PostgreSQL index optimization strategy.",
                confidence=0.98,
            ),
            DiarizedUtterance(
                speaker_index=1,
                speaker_label="Bob",
                start_time_seconds=46.0,
                end_time_seconds=90.0,
                text="I will add B-Tree indexes on user_id and meeting_id by Monday.",
                confidence=0.96,
            ),
        ],
        full_transcript="Welcome everyone. We must finalize the PostgreSQL index optimization strategy. I will add B-Tree indexes on user_id and meeting_id by Monday.",
        raw_response={},
    )

    mock_ai = MeetingIntelligenceResult(
        title="PostgreSQL Query Optimization",
        summary_short="The team agreed to add B-Tree indexes on foreign keys to accelerate dashboard queries.",
        summary_detailed="Detailed performance review. Bob agreed to create composite indexes by Monday.",
        sentiment="positive",
        sentiment_score=0.95,
        key_points=[
            KeyPointItem(point_text="Add B-Tree indexes for fast joins.", timestamp_seconds=46.0)
        ],
        action_items=[
            ActionItemDTO(
                task_description="Add composite B-Tree indexes on foreign keys",
                assigned_to="Bob",
                deadline_raw_text="by Monday",
                deadline_date="2026-08-25",
                timestamp_seconds=50.0,
            )
        ],
        decisions=[
            DecisionDTO(
                decision_text="Enforce indexing on all UUID foreign key columns",
                timestamp_seconds=48.0,
            )
        ],
        unresolved_issues=[],
        follow_up_items=[],
        deadlines=[
            DeadlineDTO(
                description="PostgreSQL indexing",
                raw_text="by Monday",
                resolved_date="2026-08-25",
                timestamp_seconds=50.0,
            )
        ],
        raw_response={},
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # Step 2: Register Primary User & Secondary User
        suffix = uuid.uuid4().hex[:8]
        user_email = f"day6_lead_{suffix}@meetingmind.ai"
        user_pw = "SecurePassword2026!"
        print(f"\n[Step 2] Registering primary user: {user_email}...")

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Day 6 Lead", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print("[OK] Primary user registered!")

        other_email = f"day6_other_{suffix}@meetingmind.ai"
        reg_other = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Other User", "email": other_email, "password": user_pw},
        )
        assert reg_other.status_code == 201
        other_token = reg_other.json()["data"]["tokens"]["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}
        print("[OK] Secondary user registered for isolation tests!")

        # Step 3: Upload meeting recording
        print("\n[Step 3] Uploading audio recording (POST /api/v1/meetings)...")
        audio_payload = b"ID3\x03\x00\x00\x00\x00\x00\x20" + (b"\xff\xfb\x90\x44" * 512)
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("db_optimization.mp3", io.BytesIO(audio_payload), "audio/mpeg")},
            data={"title": "PostgreSQL Query Optimization"},
        )
        assert upload_res.status_code == 201
        meeting_id = upload_res.json()["data"]["meeting"]["id"]
        print(f"[OK] Meeting created with id={meeting_id}")

        # Step 4: Process meeting
        print("\n[Step 4] Running full AI pipeline in background worker...")
        with patch(
            "app.worker.deepgram_service.transcribe_file",
            new=AsyncMock(return_value=mock_stt),
        ), patch(
            "app.worker.gemini_service.extract_meeting_intelligence",
            new=AsyncMock(return_value=mock_ai),
        ):
            res = await process_meeting(None, meeting_id)
            assert res["status"] == "success"
            print(f"[OK] Worker pipeline finished: {res['meeting_status']}")

        # Step 5: Test Meeting Q&A Chat (POST /api/v1/meetings/{id}/chat)
        print("\n[Step 5] Testing Meeting Q&A Chat (POST /api/v1/meetings/{id}/chat)...")
        mock_qa_resp = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "Bob stated at [00:46] that he will add B-Tree indexes on user_id and meeting_id by Monday."
                            }
                        ]
                    }
                }
            ]
        }

        with patch("app.modules.qa.service.QAService._call_gemini_api", new=AsyncMock(return_value=mock_qa_resp)):
            chat_res = await client.post(
                f"/api/v1/meetings/{meeting_id}/chat",
                headers=auth_headers,
                json={"question": "What indexes will Bob add?"},
            )
            assert chat_res.status_code == 200
            chat_data = chat_res.json()["data"]
            assert "B-Tree indexes" in chat_data["answer"]
            assert chat_data["referenced_timestamp_seconds"] == 46.0
            print(f"[OK] Q&A Answer received: '{chat_data['answer']}' (Timestamp: {chat_data['referenced_timestamp_seconds']}s)")



        # Step 6: Test Chat History (GET /api/v1/meetings/{id}/chat)
        print("\n[Step 6] Testing Chat History (GET /api/v1/meetings/{id}/chat)...")
        history_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/chat",
            headers=auth_headers,
        )
        assert history_res.status_code == 200
        history = history_res.json()["data"]
        assert len(history) == 1
        assert history[0]["question"] == "What indexes will Bob add?"
        print(f"[OK] Chat history returned {len(history)} stored message(s)")

        # Step 7: Test Dashboard Stats (GET /api/v1/dashboard/stats)
        print("\n[Step 7] Testing Dashboard Stats (GET /api/v1/dashboard/stats)...")
        stats_res = await client.get(
            "/api/v1/dashboard/stats",
            headers=auth_headers,
        )
        assert stats_res.status_code == 200
        stats = stats_res.json()["data"]
        assert stats["total_meetings"] >= 1
        assert stats["total_duration_seconds"] >= 90
        assert stats["action_items"]["total"] >= 1
        assert stats["total_decisions"] >= 1
        assert stats["sentiment"]["positive"] >= 1
        print(f"[OK] Dashboard Stats: {stats['total_meetings']} meeting(s), {stats['total_hours_formatted']}, {stats['action_items']['total']} action(s), {stats['total_decisions']} decision(s)")

        # Step 8: Test Upcoming Deadlines (GET /api/v1/dashboard/deadlines)
        print("\n[Step 8] Testing Upcoming Deadlines (GET /api/v1/dashboard/deadlines)...")
        deadlines_res = await client.get(
            "/api/v1/dashboard/deadlines",
            headers=auth_headers,
        )
        assert deadlines_res.status_code == 200
        deadlines = deadlines_res.json()["data"]
        assert len(deadlines) >= 1
        print(f"[OK] Upcoming deadlines ({len(deadlines)}): '{deadlines[0]['description']}' (Due: {deadlines[0]['resolved_date']})")

        # Step 9: Test Recent Decisions (GET /api/v1/dashboard/decisions)
        print("\n[Step 9] Testing Recent Decisions (GET /api/v1/dashboard/decisions)...")
        decisions_res = await client.get(
            "/api/v1/dashboard/decisions",
            headers=auth_headers,
        )
        assert decisions_res.status_code == 200
        decisions = decisions_res.json()["data"]
        assert len(decisions) >= 1
        print(f"[OK] Recent decisions ({len(decisions)}): '{decisions[0]['decision_text']}'")

        # Step 10: Test Recent Meetings with Enriched Counts
        print("\n[Step 10] Testing Recent Meetings with Counts (GET /api/v1/dashboard/recent-meetings)...")
        recent_res = await client.get(
            "/api/v1/dashboard/recent-meetings",
            headers=auth_headers,
        )
        assert recent_res.status_code == 200
        recent = recent_res.json()["data"]
        assert len(recent) >= 1
        print(f"[OK] Recent meeting: '{recent[0]['title']}' (Actions: {recent[0]['action_items_count']}, Decisions: {recent[0]['decisions_count']})")

        # Step 11: Test Global Search across meetings, transcripts, actions, decisions
        print("\n[Step 11] Testing Global Search (GET /api/v1/search?q=PostgreSQL)...")
        search_res = await client.get(
            "/api/v1/search?q=PostgreSQL",
            headers=auth_headers,
        )
        assert search_res.status_code == 200
        search_data = search_res.json()["data"]
        assert search_data["total_matches"] >= 1
        print(f"[OK] Global Search found {search_data['total_matches']} total match(es): {len(search_data['meetings'])} meeting(s), {len(search_data['transcripts'])} transcript segment(s), {len(search_data['action_items'])} action(s)")

        # Step 12: Test Multi-Tenant Security Isolation
        print("\n[Step 12] Testing Multi-Tenant Security Isolation...")
        other_stats = await client.get(
            "/api/v1/dashboard/stats",
            headers=other_headers,
        )
        assert other_stats.status_code == 200
        assert other_stats.json()["data"]["total_meetings"] == 0
        print("[OK] Other user sees 0 meetings and isolated stats (Total = 0)")

        other_chat = await client.get(
            f"/api/v1/meetings/{meeting_id}/chat",
            headers=other_headers,
        )
        assert other_chat.status_code == 403
        print("[OK] Other user blocked from reading meeting chat (403 Forbidden)")

    print("\n" + "=" * 65)
    print("ALL PHASE 3 DAY 6 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_verification())
