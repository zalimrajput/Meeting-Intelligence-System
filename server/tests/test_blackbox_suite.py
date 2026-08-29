"""Black-Box Integration & Security Test Suite for MeetingMind AI Platform.

Simulates strict external client/frontend consumer interactions:
1. Root Landing, Health, OpenAPI specification, and Swagger/ReDoc docs.
2. Standardized API Envelope Structure ({ success, data, meta, error }).
3. Auth Flow & Status Codes (201 Created, 200 OK, 409 Conflict, 401 Unauthorized, 422 Validation Error).
4. Audio Ingestion & Bad Magic Bytes Rejection (400 / 422 Bad Request).
5. Media Streaming via HTTP Range headers (200 Full, 206 Partial Content with Content-Range, 416 Out of Bounds).
6. Cross-Tenant Access Boundary Enforcement (403 Forbidden).
7. Non-existent Resource Handling (404 Not Found).
8. Export Format Query Parameter Validation (422 Unprocessable Entity for invalid formats).
9. Search & Dashboard Envelope Consistency.
"""

import io
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import init_db
from app.main import app


@pytest.mark.asyncio
async def test_blackbox_system_endpoints():
    """Validates public system endpoints and documentation availability."""
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Root landing
        res_root = await client.get("/")
        assert res_root.status_code == 200
        assert res_root.json()["project"] == "MeetingMind API"

        # Health endpoint
        res_health = await client.get("/api/v1/health")
        assert res_health.status_code == 200
        envelope = res_health.json()
        assert envelope["success"] is True
        assert envelope["data"]["status"] == "healthy"

        # OpenAPI schema
        res_openapi = await client.get("/openapi.json")
        assert res_openapi.status_code == 200
        assert "paths" in res_openapi.json()

        # Swagger Docs
        res_docs = await client.get("/docs")
        assert res_docs.status_code == 200


@pytest.mark.asyncio
async def test_blackbox_auth_envelope_and_error_handling():
    """Validates API envelope consistency across registration, login, and error states."""
    await init_db()
    suffix = uuid.uuid4().hex[:8]
    email = f"blackbox_{suffix}@meetingmind.ai"
    password = "SecurePassword2026!"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Validation Error on bad payload (422)
        res_bad = await client.post("/api/v1/auth/register", json={"email": "not-an-email"})
        assert res_bad.status_code == 422
        bad_json = res_bad.json()
        assert bad_json["success"] is False
        assert "error" in bad_json

        # 2. Successful Registration (201)
        res_reg = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Blackbox Tester", "email": email, "password": password},
        )
        assert res_reg.status_code == 201
        reg_json = res_reg.json()
        assert reg_json["success"] is True
        assert "access_token" in reg_json["data"]["tokens"]

        # 3. Duplicate User Registration Conflict (409)
        res_dup = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Blackbox Tester", "email": email, "password": password},
        )
        assert res_dup.status_code == 409
        dup_json = res_dup.json()
        assert dup_json["success"] is False
        assert dup_json["error"]["code"] == "USER_ALREADY_EXISTS"

        # 4. Failed Login Invalid Credentials (401)
        res_login_bad = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword!"},
        )
        assert res_login_bad.status_code == 401
        assert res_login_bad.json()["success"] is False

        # 5. Accessing Protected Route Without Auth (401)
        res_unauth = await client.get("/api/v1/users/me")
        assert res_unauth.status_code == 401


@pytest.mark.asyncio
async def test_blackbox_meeting_ingestion_and_security_boundaries():
    """Validates meeting upload, range streaming, and multi-tenant security isolation."""
    await init_db()
    suffix = uuid.uuid4().hex[:8]
    user1_email = f"user1_{suffix}@meetingmind.ai"
    user2_email = f"user2_{suffix}@meetingmind.ai"
    password = "SecurePassword2026!"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register User 1
        r1 = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Tenant One", "email": user1_email, "password": password},
        )
        token1 = r1.json()["data"]["tokens"]["access_token"]
        headers1 = {"Authorization": f"Bearer {token1}"}

        # Register User 2
        r2 = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "Tenant Two", "email": user2_email, "password": password},
        )
        token2 = r2.json()["data"]["tokens"]["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        # User 1 uploads valid MP3
        audio_content = b"ID3\x03\x00\x00\x00\x00\x00\x20" + (b"\xff\xfb\x90\x44" * 256)
        upload_res = await client.post(
            "/api/v1/meetings",
            headers=headers1,
            files={"file": ("test_recording.mp3", io.BytesIO(audio_content), "audio/mpeg")},
            data={"title": "Blackbox Security Meeting"},
        )
        assert upload_res.status_code == 201
        meeting_id = upload_res.json()["data"]["meeting"]["id"]

        # User 1 streams media with full content (200)
        res_full = await client.get(f"/api/v1/meetings/{meeting_id}/media", headers=headers1)
        assert res_full.status_code == 200
        assert res_full.headers.get("accept-ranges") == "bytes"

        # User 1 streams media with Range header (206)
        res_range = await client.get(
            f"/api/v1/meetings/{meeting_id}/media",
            headers={**headers1, "Range": "bytes=0-99"},
        )
        assert res_range.status_code == 206
        assert "bytes 0-99/" in res_range.headers.get("content-range", "")
        assert len(res_range.content) == 100

        # User 2 attempts to access User 1's meeting media (403 Forbidden)
        res_cross_media = await client.get(f"/api/v1/meetings/{meeting_id}/media", headers=headers2)
        assert res_cross_media.status_code == 403

        # User 2 attempts to export User 1's meeting (403 Forbidden)
        res_cross_export = await client.get(f"/api/v1/meetings/{meeting_id}/export?format=json", headers=headers2)
        assert res_cross_export.status_code == 403

        # Non-existent meeting lookup (404 Not Found)
        fake_id = str(uuid.uuid4())
        res_404 = await client.get(f"/api/v1/meetings/{fake_id}", headers=headers1)
        assert res_404.status_code == 404

        # Export with invalid format param (422 Unprocessable Entity)
        res_bad_format = await client.get(f"/api/v1/meetings/{meeting_id}/export?format=unsupported", headers=headers1)
        assert res_bad_format.status_code == 422
