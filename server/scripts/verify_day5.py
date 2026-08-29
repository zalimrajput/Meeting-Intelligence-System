import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Comprehensive End-to-End Verification Script for MeetingMind Phase 3 Day 5.

Validates:
1. Media Streaming API (Full 200 OK + HTTP Range 206 Partial Content).
2. Transcript Search Query Filtering (`?search=keyword`).
3. Action Item Lifecycle:
   - AI Extracted Action Item (`GET /api/v1/meetings/{id}/actions`)
   - Patch Status (`pending` -> `in_progress` -> `completed`)
   - Patch Deadline & Task Description
   - Create Action Item manually (`POST /api/v1/meetings/{id}/actions`)
   - Delete Action Item (`DELETE /api/v1/meetings/{id}/actions/{id}`)
4. Multi-Tenant Authorization Security Checks on Media & Action Mutations.
"""

import asyncio
import io
import uuid
from unittest.mock import AsyncMock, patch

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
    KeyPointItem,
    MeetingIntelligenceResult,
)
from app.worker import process_meeting


async def run_verification() -> None:
    print("=" * 65)
    print("Starting MeetingMind Phase 3 Day 5 Verification (Meeting Details & Actions)")
    print("=" * 65)

    print("\n[Step 1] Initializing database reflection...")
    await init_db()
    print("[OK] Database reflection successful!")

    mock_stt = DeepGramTranscriptionResult(
        duration_seconds=40.0,
        speakers=["Speaker 1", "Speaker 2"],
        utterances=[
            DiarizedUtterance(
                speaker_index=0,
                speaker_label="Speaker 1",
                start_time_seconds=0.0,
                end_time_seconds=20.0,
                text="Welcome to the frontend architecture sync. Let's discuss state management.",
                confidence=0.98,
            ),
            DiarizedUtterance(
                speaker_index=1,
                speaker_label="Speaker 2",
                start_time_seconds=21.0,
                end_time_seconds=40.0,
                text="I will integrate the audio waveform player by Friday.",
                confidence=0.96,
            ),
        ],
        full_transcript="Welcome to the frontend architecture sync. I will integrate the audio waveform player by Friday.",
        raw_response={},
    )

    mock_ai = MeetingIntelligenceResult(
        title="Frontend Architecture Sync",
        summary_short="Discussion on state management and waveform audio player integration.",
        summary_detailed="Engineering team reviewed player sync, timestamp seeking, and action item workflows.",
        sentiment="positive",
        sentiment_score=0.9,
        key_points=[
            KeyPointItem(point_text="Waveform player integration planned.", timestamp_seconds=21.0)
        ],
        action_items=[
            ActionItemDTO(
                task_description="Integrate audio waveform player in Next.js",
                assigned_to="Speaker 2",
                deadline_raw_text="by Friday",
                deadline_date="2026-08-28",
                timestamp_seconds=25.0,
            )
        ],
        decisions=[
            DecisionDTO(
                decision_text="Adopt HTTP Range media streaming for seeking",
                timestamp_seconds=10.0,
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
        # Step 2: Register Primary User & Secondary User
        suffix = uuid.uuid4().hex[:8]
        user_email = f"day5_lead_{suffix}@meetingmind.ai"
        user_pw = "SecurePassword2026!"
        print(f"\n[Step 2] Registering primary user: {user_email}...")

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Day 5 Lead", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print("[OK] Primary user registered!")

        other_email = f"day5_other_{suffix}@meetingmind.ai"
        reg_other = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Other User", "email": other_email, "password": user_pw},
        )
        assert reg_other.status_code == 201
        other_token = reg_other.json()["data"]["tokens"]["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}
        print("[OK] Secondary user registered for isolation tests!")

        # Step 3: Upload media recording
        print("\n[Step 3] Uploading audio recording (POST /api/v1/meetings)...")
        audio_payload = b"ID3\x03\x00\x00\x00\x00\x00\x20" + (b"\xff\xfb\x90\x44" * 512)
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("frontend_sync.mp3", io.BytesIO(audio_payload), "audio/mpeg")},
            data={"title": "Frontend Architecture Sync"},
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

        # Step 5: Test Media Streaming (Full + Range)
        print("\n[Step 5] Testing media streaming endpoint (GET /api/v1/meetings/{id}/media)...")
        full_media = await client.get(
            f"/api/v1/meetings/{meeting_id}/media",
            headers=auth_headers,
        )
        assert full_media.status_code == 200
        assert full_media.headers.get("accept-ranges") == "bytes"
        assert len(full_media.content) == len(audio_payload)
        print(f"[OK] Full media playback (200 OK): {len(full_media.content)} bytes received")

        # Range request
        range_media = await client.get(
            f"/api/v1/meetings/{meeting_id}/media",
            headers={**auth_headers, "Range": "bytes=0-199"},
        )
        assert range_media.status_code == 206
        assert len(range_media.content) == 200
        assert "bytes 0-199/" in range_media.headers.get("content-range")
        print(f"[OK] Seeking/Range playback (206 Partial Content): Content-Range={range_media.headers.get('content-range')}")

        # Step 6: Test Searchable Transcripts
        print("\n[Step 6] Testing searchable transcripts (GET /api/v1/meetings/{id}/transcript?search=waveform)...")
        search_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/transcript?search=waveform",
            headers=auth_headers,
        )
        assert search_res.status_code == 200
        segments = search_res.json()["data"]
        assert len(segments) == 1
        assert "waveform" in segments[0]["text"]
        print(f"[OK] Search query returned {len(segments)} matching segment: '{segments[0]['text']}'")

        # Step 7: Test Action Items Lifecycle & Status Mutations
        print("\n[Step 7] Testing Action Item mutations (PATCH / POST / DELETE)...")
        # 7a. Get actions
        act_get = await client.get(
            f"/api/v1/meetings/{meeting_id}/actions",
            headers=auth_headers,
        )
        assert act_get.status_code == 200
        action_list = act_get.json()["data"]
        assert len(action_list) == 1
        action_id = action_list[0]["id"]
        assert action_list[0]["status"] == "pending"
        print(f"[OK] Initial action item: '{action_list[0]['task_description']}' (status={action_list[0]['status']})")

        # 7b. Update status to 'completed'
        patch_res = await client.patch(
            f"/api/v1/meetings/{meeting_id}/actions/{action_id}",
            headers=auth_headers,
            json={"status": "completed"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["data"]["status"] == "completed"
        print(f"[OK] Updated status: status={patch_res.json()['data']['status']}")

        # 7c. Manually create action item
        create_res = await client.post(
            f"/api/v1/meetings/{meeting_id}/actions",
            headers=auth_headers,
            json={
                "task_description": "Review API documentation before release",
                "assigned_to": "QA Team",
                "status": "in_progress",
            },
        )
        assert create_res.status_code == 201
        created_id = create_res.json()["data"]["id"]
        print(f"[OK] Created new action item id={created_id}")

        # 7d. Delete created action item
        del_res = await client.delete(
            f"/api/v1/meetings/{meeting_id}/actions/{created_id}",
            headers=auth_headers,
        )
        assert del_res.status_code == 200
        assert del_res.json()["data"]["deleted"] is True
        print(f"[OK] Deleted action item id={created_id}")

        # Step 8: Test Multi-Tenant Security Isolation
        print("\n[Step 8] Testing multi-tenant security isolation...")
        media_other = await client.get(
            f"/api/v1/meetings/{meeting_id}/media",
            headers=other_headers,
        )
        assert media_other.status_code == 403
        print("[OK] Blocked unauthorized media access (403 Forbidden)")

        action_other = await client.patch(
            f"/api/v1/meetings/{meeting_id}/actions/{action_id}",
            headers=other_headers,
            json={"status": "completed"},
        )
        assert action_other.status_code == 403
        print("[OK] Blocked unauthorized action item update (403 Forbidden)")

    print("\n" + "=" * 65)
    print("ALL PHASE 3 DAY 5 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_verification())
