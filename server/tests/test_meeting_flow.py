"""Tests for MeetingMind Phase 1 Day 2: File uploads, storage, job queue, and lifecycle."""

import hashlib
import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import init_db
from app.main import app


@pytest.mark.asyncio
async def test_full_meeting_upload_and_lifecycle() -> None:
    """Tests the full Day 2 meeting lifecycle: upload, status polling, and deletion."""
    await init_db()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Register test user
        unique_suffix = uuid.uuid4().hex[:8]
        user_email = f"uploader_{unique_suffix}@meetingmind.ai"
        user_password = "SecurePassword123!"
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Test Uploader",
                "email": user_email,
                "password": user_password,
            },
        )
        assert reg_res.status_code == 201
        token = reg_res.json()["data"]["tokens"]["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # Register second user for isolation tests
        other_email = f"other_{unique_suffix}@meetingmind.ai"
        other_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Other User",
                "email": other_email,
                "password": user_password,
            },
        )
        assert other_reg.status_code == 201
        other_token = other_reg.json()["data"]["tokens"]["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # 2. Test uploading invalid file format (e.g. plain text / invalid magic bytes)
        invalid_bytes = b"This is just plain text, not a valid audio or video file format!"
        invalid_file = io.BytesIO(invalid_bytes)
        bad_upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("invalid.mp3", invalid_file, "audio/mpeg")},
            data={"title": "Invalid Recording"},
        )
        assert bad_upload_res.status_code == 400
        bad_data = bad_upload_res.json()
        assert bad_data["success"] is False
        assert bad_data["error"]["code"] == "INVALID_FILE_TYPE"

        # 3. Test uploading valid audio recording (ID3 MP3 header)
        valid_mp3_content = b"ID3\x03\x00\x00\x00\x00\x00\x10" + b"\xff\xfb\x90\x44" * 100
        valid_file = io.BytesIO(valid_mp3_content)
        expected_checksum = hashlib.sha256(valid_mp3_content).hexdigest()

        upload_res = await client.post(
            "/api/v1/meetings",
            headers=auth_headers,
            files={"file": ("weekly_sync.mp3", valid_file, "audio/mpeg")},
            data={"title": "Q3 Engineering Sync"},
        )
        assert upload_res.status_code == 201
        upload_data = upload_res.json()
        assert upload_data["success"] is True

        meeting_payload = upload_data["data"]["meeting"]
        file_payload = upload_data["data"]["file"]
        job_payload = upload_data["data"]["job"]

        meeting_id = meeting_payload["id"]
        assert meeting_payload["title"] == "Q3 Engineering Sync"
        assert meeting_payload["status"] == "uploaded"

        assert file_payload["file_type"] == "audio"
        assert file_payload["original_filename"] == "weekly_sync.mp3"
        assert file_payload["checksum"] == expected_checksum
        assert file_payload["size_bytes"] == len(valid_mp3_content)

        assert job_payload["stage"] == "transcription"
        assert job_payload["status"] == "queued"

        # 4. Test polling GET /api/v1/meetings/{id}/status
        status_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/status",
            headers=auth_headers,
        )
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["success"] is True
        assert status_data["data"]["meeting_id"] == meeting_id
        assert len(status_data["data"]["jobs"]) >= 1
        assert status_data["data"]["jobs"][0]["stage"] == "transcription"

        # 5. Test user isolation: Other user cannot access meeting details or status
        other_get_res = await client.get(
            f"/api/v1/meetings/{meeting_id}",
            headers=other_headers,
        )
        assert other_get_res.status_code == 403
        assert other_get_res.json()["error"]["code"] == "FORBIDDEN_RESOURCE"

        other_status_res = await client.get(
            f"/api/v1/meetings/{meeting_id}/status",
            headers=other_headers,
        )
        assert other_status_res.status_code == 403
        assert other_status_res.json()["error"]["code"] == "FORBIDDEN_RESOURCE"

        # 6. Test listing meetings for owner
        list_res = await client.get(
            "/api/v1/meetings",
            headers=auth_headers,
        )
        assert list_res.status_code == 200
        list_data = list_res.json()
        assert list_data["success"] is True
        meeting_ids = [m["id"] for m in list_data["data"]]
        assert meeting_id in meeting_ids

        # 7. Test hard delete: DELETE /api/v1/meetings/{id}
        del_res = await client.delete(
            f"/api/v1/meetings/{meeting_id}",
            headers=auth_headers,
        )
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

        # 8. Verify meeting is gone
        post_del_res = await client.get(
            f"/api/v1/meetings/{meeting_id}",
            headers=auth_headers,
        )
        assert post_del_res.status_code == 404
        assert post_del_res.json()["error"]["code"] == "MEETING_NOT_FOUND"
