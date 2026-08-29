"""Comprehensive test suite for MeetingMind authentication and API envelope."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import init_db
from app.main import app


@pytest.mark.asyncio
async def test_full_application_suite() -> None:
    """Runs end-to-end test suite for health, registration, login, refresh, and protection."""
    await init_db()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        # 1. Health check
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["data"]["status"] == "healthy"
        assert data["data"]["version"] == "1.0.0"

        # 2. Registration
        unique_suffix = uuid.uuid4().hex[:8]
        test_email = f"testuser_{unique_suffix}@meetingmind.ai"
        test_password = "SecurePassword123!"
        test_name = "Alex Johnson"

        reg_payload = {
            "full_name": test_name,
            "email": test_email,
            "password": test_password,
        }
        reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_res.status_code == 201
        reg_data = reg_res.json()
        assert reg_data["success"] is True
        assert reg_data["data"]["user"]["email"] == test_email
        assert reg_data["data"]["user"]["full_name"] == test_name
        assert "password" not in reg_data["data"]["user"]
        assert "password_hash" not in reg_data["data"]["user"]
        assert "access_token" in reg_data["data"]["tokens"]
        assert "refresh_token" in reg_data["data"]["tokens"]

        # 3. Duplicate Registration
        dup_res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert dup_res.status_code == 409
        dup_data = dup_res.json()
        assert dup_data["success"] is False
        assert dup_data["error"]["code"] == "USER_ALREADY_EXISTS"

        # 4. Validation failure
        invalid_res = await client.post(
            "/api/v1/auth/register",
            json={"full_name": "A", "email": "not-an-email", "password": "short"},
        )
        assert invalid_res.status_code == 422
        invalid_data = invalid_res.json()
        assert invalid_data["success"] is False
        assert invalid_data["error"]["code"] == "VALIDATION_ERROR"
        assert "errors" in invalid_data["error"]["details"]

        # 5. Wrong password login
        wrong_pwd_res = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": "WrongPassword!"},
        )
        assert wrong_pwd_res.status_code == 401
        wrong_pwd_data = wrong_pwd_res.json()
        assert wrong_pwd_data["success"] is False
        assert wrong_pwd_data["error"]["code"] == "INVALID_CREDENTIALS"

        # 6. Correct login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": test_email, "password": test_password},
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        assert login_data["success"] is True
        login_access_token = login_data["data"]["tokens"]["access_token"]
        login_refresh_token = login_data["data"]["tokens"]["refresh_token"]

        # 7. Protected route
        profile_res = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {login_access_token}"},
        )
        assert profile_res.status_code == 200
        profile_data = profile_res.json()
        assert profile_data["success"] is True
        assert profile_data["data"]["email"] == test_email

        # 8. Unauthenticated access
        no_auth_res = await client.get("/api/v1/users/me")
        assert no_auth_res.status_code == 401
        no_auth_data = no_auth_res.json()
        assert no_auth_data["success"] is False
        assert no_auth_data["error"]["code"] == "UNAUTHORIZED"

        # 9. Invalid token access
        bad_token_res = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid.token.value"},
        )
        assert bad_token_res.status_code == 401
        bad_token_data = bad_token_res.json()
        assert bad_token_data["success"] is False
        assert bad_token_data["error"]["code"] == "INVALID_TOKEN"

        # 10. Refresh token rotation
        refresh_res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_refresh_token},
        )
        assert refresh_res.status_code == 200
        refresh_data = refresh_res.json()
        assert refresh_data["success"] is True
        new_access_token = refresh_data["data"]["access_token"]
        new_refresh_token = refresh_data["data"]["refresh_token"]
        assert new_access_token != login_access_token
        assert new_refresh_token != login_refresh_token

        # 11. Rotated access token works on protected route
        new_profile_res = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        assert new_profile_res.status_code == 200

        # 12. Password reset request
        forgot_res = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_email},
        )
        assert forgot_res.status_code == 200
        forgot_data = forgot_res.json()
        assert forgot_data["success"] is True
        assert "message" in forgot_data["data"]
