import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

"""Standalone end-to-end verification script for MeetingMind Authentication & Protected Routes."""

import asyncio
import uuid

from httpx import ASGITransport, AsyncClient

from app.core.database import init_db
from app.main import app


async def run_verification() -> None:
    print("=" * 60)
    print("Starting MeetingMind Authentication & API Verification")
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
        health_res = await client.get("/api/v1/health")
        assert health_res.status_code == 200, f"Health check failed: {health_res.text}"
        health_data = health_res.json()
        assert health_data["success"] is True
        print(f"[OK] Health Check OK: {health_data}")

        # 3. User Registration
        unique_suffix = uuid.uuid4().hex[:6]
        test_email = f"developer_{unique_suffix}@meetingmind.ai"
        test_password = "SecurePassword123!"
        test_full_name = "Alex Vance"

        print(f"\n[Step 3] Testing POST /api/v1/auth/register with email={test_email}...")
        reg_res = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": test_full_name,
                "email": test_email,
                "password": test_password,
            },
        )
        assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"
        reg_data = reg_res.json()
        assert reg_data["success"] is True
        assert reg_data["data"]["user"]["email"] == test_email
        assert reg_data["data"]["user"]["full_name"] == test_full_name
        assert "password" not in reg_data["data"]["user"]
        assert "password_hash" not in reg_data["data"]["user"]
        print(f"[OK] Registered User: id={reg_data['data']['user']['id']}, email={test_email}")
        print(f"[OK] Issued Access Token (expires in {reg_data['data']['tokens']['expires_in']}s)")
        print("[OK] Issued Refresh Token")

        # 4. Duplicate Registration (Should Fail with 409 USER_ALREADY_EXISTS)
        print("\n[Step 4] Testing duplicate registration rejection...")
        dup_res = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": test_full_name,
                "email": test_email,
                "password": test_password,
            },
        )
        assert dup_res.status_code == 409, f"Expected 409 conflict, got: {dup_res.status_code}"
        dup_data = dup_res.json()
        assert dup_data["success"] is False
        assert dup_data["error"]["code"] == "USER_ALREADY_EXISTS"
        print(f"[OK] Correctly rejected: {dup_data['error']['message']}")

        # 5. Validation Failure
        print("\n[Step 5] Testing Zod/Pydantic validation failure envelope...")
        invalid_res = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "A",
                "email": "not-an-email",
                "password": "short",
            },
        )
        assert (
            invalid_res.status_code == 422
        ), f"Expected 422 validation error, got: {invalid_res.status_code}"
        invalid_data = invalid_res.json()
        assert invalid_data["success"] is False
        assert invalid_data["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in invalid_data["error"]
        print(f"[OK] Correctly formatted validation error: {invalid_data['error']}")

        # 6. User Login (Success)
        print("\n[Step 6] Testing POST /api/v1/auth/login with valid credentials...")
        login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_email,
                "password": test_password,
            },
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        login_data = login_res.json()
        assert login_data["success"] is True
        access_token = login_data["data"]["tokens"]["access_token"]
        refresh_token = login_data["data"]["tokens"]["refresh_token"]
        print(f"[OK] Login successful! Token type: {login_data['data']['tokens']['token_type']}")

        # 7. User Login (Failure with wrong password)
        print("\n[Step 7] Testing login failure with wrong password...")
        bad_login_res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": test_email,
                "password": "WrongPassword123!",
            },
        )
        assert bad_login_res.status_code == 401, f"Expected 401, got {bad_login_res.status_code}"
        bad_login_data = bad_login_res.json()
        assert bad_login_data["success"] is False
        assert bad_login_data["error"]["code"] == "INVALID_CREDENTIALS"
        print(f"[OK] Correctly rejected: {bad_login_data['error']['message']}")

        # 8. Access Protected Route GET /api/v1/users/me
        print("\n[Step 8] Testing protected route GET /api/v1/users/me with valid Bearer token...")
        me_res = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_res.status_code == 200, f"Protected route failed: {me_res.text}"
        me_data = me_res.json()
        assert me_data["success"] is True
        assert me_data["data"]["email"] == test_email
        print(f"[OK] Authenticated user profile retrieved: email={me_data['data']['email']}")

        # 9. Access Protected Route without token
        print("\n[Step 9] Testing protected route without Authorization header...")
        no_auth_res = await client.get("/api/v1/users/me")
        assert (
            no_auth_res.status_code == 401
        ), f"Expected 401 Unauthorized, got: {no_auth_res.status_code}"
        no_auth_data = no_auth_res.json()
        assert no_auth_data["success"] is False
        assert no_auth_data["error"]["code"] == "UNAUTHORIZED"
        print(f"[OK] Correctly blocked: {no_auth_data['error']['message']}")

        # 10. Access Protected Route with invalid token
        print("\n[Step 10] Testing protected route with invalid/tampered token...")
        bad_token_res = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.tampered.token"},
        )
        assert (
            bad_token_res.status_code == 401
        ), f"Expected 401 Unauthorized, got: {bad_token_res.status_code}"
        bad_token_data = bad_token_res.json()
        assert bad_token_data["success"] is False
        assert bad_token_data["error"]["code"] == "INVALID_TOKEN"
        print(f"[OK] Correctly blocked: {bad_token_data['error']['message']}")

        # 11. Refresh Token Rotation
        print("\n[Step 11] Testing refresh token rotation POST /api/v1/auth/refresh...")
        refresh_res = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_res.status_code == 200, f"Refresh token rotation failed: {refresh_res.text}"
        refresh_data = refresh_res.json()
        assert refresh_data["success"] is True
        new_access_token = refresh_data["data"]["access_token"]
        new_refresh_token = refresh_data["data"]["refresh_token"]
        assert new_access_token != access_token
        assert new_refresh_token != refresh_token
        print("[OK] Successfully rotated tokens! Issued new access and refresh tokens.")

        # 12. Test Protected Route with newly rotated token
        print("\n[Step 12] Testing protected route with new rotated access token...")
        me_after_refresh_res = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        assert me_after_refresh_res.status_code == 200
        print("[OK] Rotated access token authenticated successfully!")

        # 13. Forgot Password
        print(f"\n[Step 13] Testing POST /api/v1/auth/forgot-password with email={test_email}...")
        forgot_res = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_email},
        )
        assert forgot_res.status_code == 200, f"Forgot password failed: {forgot_res.text}"
        forgot_data = forgot_res.json()
        assert forgot_data["success"] is True
        print(f"[OK] Forgot password response: {forgot_data['data']['message']}")

        # 14. List Meetings (Empty initially for new user)
        print("\n[Step 14] Testing user-isolated meetings query GET /api/v1/meetings...")
        meetings_res = await client.get(
            "/api/v1/meetings",
            headers={"Authorization": f"Bearer {new_access_token}"},
        )
        assert meetings_res.status_code == 200, f"Meetings query failed: {meetings_res.text}"
        meetings_data = meetings_res.json()
        assert meetings_data["success"] is True
        assert isinstance(meetings_data["data"], list)
        count = len(meetings_data["data"])
        print(f"[OK] Retrieved user meetings (count={count}, meta={meetings_data.get('meta')})")

    print("\n" + "=" * 60)
    print("ALL 14 VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_verification())
