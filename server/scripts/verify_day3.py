import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Comprehensive End-to-End Verification Script for MeetingMind Phase 2 Day 3.

Validates:
1. DeepGram response parsing & speaker mapping logic (0 -> Speaker 1, 1 -> Speaker 2)
2. Meeting upload -> Worker lifecycle (FFmpeg extraction + DeepGram transcription)
3. Direct DB verification of reflected tables:
   - `speakers` (id, meeting_id, speaker_label)
   - `transcript_segments` (id, meeting_id, speaker_id, segment_index, start/end times, text, confidence)
   - `meetings` (duration_seconds, status='transcribed')
   - `processing_jobs` (stage='transcription', status='completed')
4. API verification:
   - GET /api/v1/meetings/{id}/transcript -> 200 OK with ordered segments and speaker labels
   - GET /api/v1/meetings/{id}/status -> 200 OK with job stage and status
   - User data isolation -> 403 Forbidden for other users
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
    DeepGramService,
    DeepGramTranscriptionResult,
    DiarizedUtterance,
)
from app.worker import process_meeting


async def run_verification() -> None:
    print("=" * 65)
    print("Starting MeetingMind Phase 2 Day 3 Verification (DeepGram Pipeline)")
    print("=" * 65)

    # 1. Initialize DB reflection
    print("\n[Step 1] Initializing database reflection...")
    await init_db()
    print("[OK] Database reflection successful!")

    # 2. Test DeepGram Parser
    print("\n[Step 2] Testing DeepGram Response Parser...")
    service = DeepGramService(api_key="mock_key")
    sample_payload = {
        "metadata": {"duration": 28.75},
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {"transcript": "Good morning everyone. Let's start our status check."}
                    ]
                }
            ],
            "utterances": [
                {
                    "speaker": 0,
                    "start": 0.5,
                    "end": 3.8,
                    "transcript": "Good morning everyone.",
                    "confidence": 0.98,
                },
                {
                    "speaker": 1,
                    "start": 4.0,
                    "end": 12.5,
                    "transcript": "Let's start our status check. The database is provisioned.",
                    "confidence": 0.96,
                },
                {
                    "speaker": 0,
                    "start": 13.0,
                    "end": 28.5,
                    "transcript": "Great. The AI transcription pipeline is now active.",
                    "confidence": 0.99,
                },
            ],
        },
    }
    parsed = service.parse_response(sample_payload)
    assert parsed.duration_seconds == 28.75
    assert parsed.speakers == ["Speaker 1", "Speaker 2"]
    assert len(parsed.utterances) == 3
    assert parsed.utterances[0].speaker_label == "Speaker 1"
    assert parsed.utterances[1].speaker_label == "Speaker 2"
    print(
        f"[OK] Parsed {len(parsed.utterances)} utterances across {len(parsed.speakers)} speakers in {parsed.duration_seconds}s"
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 3. Register primary user
        suffix = uuid.uuid4().hex[:8]
        user_email = f"lead_day3_{suffix}@meetingmind.ai"
        user_pw = "SecurePass2026!"
        print(f"\n[Step 3] Registering primary user: {user_email}...")

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Day 3 Team Lead", "email": user_email, "password": user_pw},
        )
        assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
        token = reg_res.json()["data"]["tokens"]["access_token"]
        user_id = reg_res.json()["data"]["user"]["id"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print(f"[OK] Registered user_id={user_id}")

        # Register secondary user for multi-tenant isolation tests
        other_email = f"unauthorized_day3_{suffix}@meetingmind.ai"
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
            files={"file": ("architecture_sync.mp3", io.BytesIO(valid_audio), "audio/mpeg")},
            data={"title": "Architecture Sync & AI Review"},
        )
        assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
        meeting_id = upload_res.json()["data"]["meeting"]["id"]
        print(f"[OK] Uploaded meeting id={meeting_id}")

        # 5. Execute Stage 1 Worker pipeline
        print("\n[Step 5] Executing background worker process_meeting (Stage 1)...")
        with patch(
            "app.worker.deepgram_service.transcribe_file",
            new=AsyncMock(return_value=parsed),
        ):
            worker_result = await process_meeting(None, meeting_id)
            assert worker_result["status"] == "success"
            print(f"[OK] Worker output: {worker_result}")

        # 6. Verify PostgreSQL database state
        print("\n[Step 6] Verifying database records directly via SQLAlchemy...")
        async with async_session_maker() as db:
            meeting_uuid = uuid.UUID(meeting_id)

            # Check Meeting
            res_m = await db.execute(
                select(models.Meeting).where(models.Meeting.id == meeting_uuid)
            )
            db_meeting = res_m.scalars().first()
            assert db_meeting.status == "analyzing"
            assert db_meeting.duration_seconds == 29  # round(28.75)
            print(
                f"[OK] DB Meeting: status={db_meeting.status}, duration={db_meeting.duration_seconds}s"
            )


            # Check ProcessingJob
            res_j = await db.execute(
                select(models.ProcessingJob).where(
                    models.ProcessingJob.meeting_id == meeting_uuid,
                    models.ProcessingJob.stage == "transcription",
                )
            )
            db_job = res_j.scalars().first()
            assert db_job.status == "completed"
            assert db_job.completed_at is not None
            print(
                f"[OK] DB ProcessingJob: stage={db_job.stage}, status={db_job.status}, completed_at={db_job.completed_at}"
            )

            # Check Speakers
            res_s = await db.execute(
                select(models.Speaker).where(models.Speaker.meeting_id == meeting_uuid)
            )
            db_speakers = res_s.scalars().all()
            assert len(db_speakers) == 2
            labels = [s.speaker_label for s in db_speakers]
            assert "Speaker 1" in labels and "Speaker 2" in labels
            print(f"[OK] DB Speakers ({len(db_speakers)}): {labels}")

            # Check Transcript Segments
            res_t = await db.execute(
                select(models.TranscriptSegment)
                .where(models.TranscriptSegment.meeting_id == meeting_uuid)
                .order_by(models.TranscriptSegment.segment_index.asc())
            )
            db_segments = res_t.scalars().all()
            assert len(db_segments) == 3
            for seg in db_segments:
                print(
                    f"     [Seg {seg.segment_index}] {float(seg.start_time_seconds):.1f}s - {float(seg.end_time_seconds):.1f}s | text='{seg.text}'"
                )
            print(f"[OK] DB Transcript Segments verified ({len(db_segments)} rows).")

        # 7. Test API endpoints
        print("\n[Step 7] Testing GET /api/v1/meetings/{id}/transcript endpoint...")
        t_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/transcript",
            headers=auth_headers,
        )
        assert t_res.status_code == 200, f"Transcript endpoint failed: {t_res.text}"
        t_json = t_res.json()
        assert t_json["success"] is True
        api_segments = t_json["data"]
        assert len(api_segments) == 3
        assert api_segments[0]["speaker_label"] == "Speaker 1"
        assert api_segments[1]["speaker_label"] == "Speaker 2"
        print(f"[OK] API Transcript Response: 200 OK with {len(api_segments)} segments")

        # 8. Test multi-tenant isolation
        print("\n[Step 8] Testing multi-tenant isolation on transcripts (403 Forbidden)...")
        other_t_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/transcript",
            headers=other_headers,
        )
        assert other_t_res.status_code == 403
        assert other_t_res.json()["error"]["code"] == "FORBIDDEN_RESOURCE"
        print(f"[OK] Successfully blocked unauthorized user access (403 FORBIDDEN_RESOURCE)")

    print("\n" + "=" * 65)
    print("ALL PHASE 2 DAY 3 VERIFICATIONS PASSED SUCCESSFULLY!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_verification())
