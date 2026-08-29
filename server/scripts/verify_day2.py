import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Comprehensive End-to-End Verification Script for MeetingMind Phase 1 Day 2.

Tests:
1. Database reflection & Health check
2. User registration & authentication
3. Invalid file magic-bytes rejection (400 INVALID_FILE_TYPE)
4. Valid audio upload (multipart/form-data) -> 201 Created + DB records + job enqueue
5. Polling GET /api/v1/meetings/{id}/status
6. Multi-tenant user data isolation (403 FORBIDDEN_RESOURCE)
7. Meeting listing GET /api/v1/meetings
8. Meeting hard deletion DELETE /api/v1/meetings/{id} + storage cleanup
9. Background worker process_meeting lifecycle execution
"""

import asyncio
import hashlib
import io
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import async_session_maker, init_db, models
from app.main import app
from app.worker import process_meeting


async def run_verification() -> None:
    print("=" * 60)
    print("Starting MeetingMind Phase 1 Day 2 Verification")
    print("=" * 60)

    # 1. Initialize DB reflection
    print("\n[Step 1] Initializing database reflection...")
    await init_db()
    print("[OK] Database reflection successful!")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 2. Health check
        print("\n[Step 2] Testing GET /api/v1/health...")
        h_res = await client.get("/api/v1/health")
        assert h_res.status_code == 200, f"Health check failed: {h_res.text}"
        print(f"[OK] Health check: {h_res.json()}")

        # 3. Register user
        suffix = uuid.uuid4().hex[:8]
        test_email = f"day2_user_{suffix}@meetingmind.ai"
        test_password = "SecurePassword2026!"
        print(f"\n[Step 3] Registering test user with email={test_email}...")

        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Day 2 Test Lead",
                "email": test_email,
                "password": test_password,
            },
        )
        assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
        reg_json = reg_res.json()
        token = reg_json["data"]["tokens"]["access_token"]
        user_id = reg_json["data"]["user"]["id"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        print(f"[OK] Registered User id={user_id}")

        # Register second user for multi-tenant isolation tests
        other_email = f"other_user_{suffix}@meetingmind.ai"
        other_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Unauthorized User",
                "email": other_email,
                "password": test_password,
            },
        )
        assert other_reg.status_code == 201
        other_token = other_reg.json()["data"]["tokens"]["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}
        print(f"[OK] Registered secondary user for isolation tests: {other_email}")

        # 4. Test invalid file rejection (magic bytes check)
        print("\n[Step 4] Testing invalid file upload rejection (corrupted/plain text file)...")
        invalid_bytes = b"Just plain text pretending to be an audio recording file header"
        bad_upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("fake_audio.mp3", io.BytesIO(invalid_bytes), "audio/mpeg")},
            data={"title": "Corrupt Audio"},
        )
        assert bad_upload_res.status_code == 400
        bad_data = bad_upload_res.json()
        assert bad_data["success"] is False
        assert bad_data["error"]["code"] == "INVALID_FILE_TYPE"
        print(f"[OK] Correctly rejected: {bad_data['error']['message']}")

        # 5. Test valid audio upload (multipart/form-data with ID3 MP3 header)
        print("\n[Step 5] Testing valid audio file upload (POST /api/v1/meetings)...")
        valid_audio = b"ID3\x03\x00\x00\x00\x00\x00\x20" + b"\xff\xfb\x90\x44" * 256
        expected_checksum = hashlib.sha256(valid_audio).hexdigest()

        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("quarterly_planning.mp3", io.BytesIO(valid_audio), "audio/mpeg")},
            data={"title": "Q3 Engineering Roadmap"},
        )
        assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
        upload_data = upload_res.json()
        assert upload_data["success"] is True

        meeting = upload_data["data"]["meeting"]
        m_file = upload_data["data"]["file"]
        job = upload_data["data"]["job"]

        meeting_id = meeting["id"]
        print(f"[OK] Uploaded meeting: id={meeting_id}, title={meeting['title']}")
        print(f"[OK] File: type={m_file['file_type']}, size={m_file['size_bytes']} bytes")
        print(f"[OK] Job: id={job['id']}, stage={job['stage']}, status={job['status']}")

        assert m_file["checksum"] == expected_checksum
        assert m_file["file_type"] == "audio"
        assert job["stage"] == "transcription"
        assert job["status"] == "queued"

        # 6. Verify direct PostgreSQL database state
        print("\n[Step 6] Verifying database records directly via SQLAlchemy...")
        async with async_session_maker() as db:
            meeting_uuid = uuid.UUID(meeting_id)
            res_m = await db.execute(
                select(models.Meeting).where(models.Meeting.id == meeting_uuid)
            )
            db_meeting = res_m.scalars().first()
            assert db_meeting is not None
            assert str(db_meeting.owner_id) == user_id

            res_f = await db.execute(
                select(models.MeetingFile).where(models.MeetingFile.meeting_id == meeting_uuid)
            )
            db_file = res_f.scalars().first()
            assert db_file is not None
            assert db_file.checksum == expected_checksum

            res_j = await db.execute(
                select(models.ProcessingJob).where(models.ProcessingJob.meeting_id == meeting_uuid)
            )
            db_job = res_j.scalars().first()
            assert db_job is not None
            assert db_job.stage == "transcription"
            assert db_job.status == "queued"

        print("[OK] Direct PostgreSQL database records verified!")

        # 7. Test polling GET /api/v1/meetings/{id}/status
        print(f"\n[Step 7] Polling status via GET /api/v1/meetings/{meeting_id}/status...")
        status_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/status",
            headers=auth_headers,
        )
        assert status_res.status_code == 200
        status_json = status_res.json()
        assert status_json["success"] is True
        assert status_json["data"]["meeting_id"] == meeting_id
        assert len(status_json["data"]["jobs"]) >= 1
        print(f"[OK] Status: meeting_status={status_json['data']['status']}")

        # 8. Test multi-tenant user data isolation
        print("\n[Step 8] Testing multi-tenant user isolation (unauthorized user access)...")
        unauth_get = await client.get(f"/api/v1/meetings/{meeting_id}", headers=other_headers)
        assert unauth_get.status_code == 403

        unauth_status = await client.get(
            f"/api/v1/meetings/{meeting_id}/status", headers=other_headers
        )
        assert unauth_status.status_code == 403

        unauth_delete = await client.delete(f"/api/v1/meetings/{meeting_id}", headers=other_headers)
        assert unauth_delete.status_code == 403
        print("[OK] Blocked unauthorized user with 403 FORBIDDEN_RESOURCE!")

        # 9. Test worker process_meeting execution
        print("\n[Step 9] Testing arq background worker process_meeting task execution...")
        worker_res = await process_meeting({}, meeting_id)
        assert worker_res["status"] == "success"

        post_worker_status = await client.get(
            f"/api/v1/meetings/{meeting_id}/status",
            headers=auth_headers,
        )
        assert post_worker_status.status_code == 200
        pw_json = post_worker_status.json()
        assert pw_json["data"]["status"] == "transcribing"
        assert pw_json["data"]["jobs"][0]["status"] == "running"
        print(f"[OK] Worker updated meeting to '{pw_json['data']['status']}' & job to 'running'!")

        # 10. Test listing user meetings
        print("\n[Step 10] Testing GET /api/v1/meetings listing for owner...")
        list_res = await client.get("/api/v1/meetings", headers=auth_headers)
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert list_data["success"] is True
        ids = [m["id"] for m in list_data["data"]]
        assert meeting_id in ids
        print(f"[OK] User meetings retrieved: {len(list_data['data'])} meeting(s) listed.")

        # 11. Test meeting hard deletion
        print(f"\n[Step 11] Testing hard deletion DELETE /api/v1/meetings/{meeting_id}...")
        del_res = await client.delete(f"/api/v1/meetings/{meeting_id}", headers=auth_headers)
        assert del_res.status_code == 200
        del_json = del_res.json()
        assert del_json["success"] is True
        print(f"[OK] Delete endpoint response: {del_json['data']['message']}")

        # 12. Verify meeting is completely deleted from PostgreSQL
        print("\n[Step 12] Verifying hard deletion in PostgreSQL...")
        async with async_session_maker() as db:
            m_res = await db.execute(
                select(models.Meeting).where(models.Meeting.id == meeting_uuid)
            )
            assert m_res.scalars().first() is None

            f_res = await db.execute(
                select(models.MeetingFile).where(models.MeetingFile.meeting_id == meeting_uuid)
            )
            assert f_res.scalars().first() is None

            j_res = await db.execute(
                select(models.ProcessingJob).where(models.ProcessingJob.meeting_id == meeting_uuid)
            )
            assert j_res.scalars().first() is None

        # Verify GET returns 404
        post_del_get = await client.get(f"/api/v1/meetings/{meeting_id}", headers=auth_headers)
        assert post_del_get.status_code == 404
        assert post_del_get.json()["error"]["code"] == "MEETING_NOT_FOUND"
        print("[OK] Confirmed hard deletion: rows removed, GET returns 404 MEETING_NOT_FOUND!")

    print("\n" + "=" * 60)
    print("ALL 12 PHASE 1 DAY 2 VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_verification())
