"""Pydantic v2 schemas for Authentication endpoints and models."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

T = TypeVar("T")


class RegisterRequest(BaseModel):
    """Payload for user registration."""

    full_name: str = Field(..., min_length=2, max_length=150, description="Full name of the user")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(
        ..., min_length=8, max_length=128, description="User password (min 8 characters)"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_name_alias(cls, data: Any) -> Any:
        """Allow 'name' as an alias for 'full_name' for frontend flexibility."""
        if isinstance(data, dict):
            if "name" in data and "full_name" not in data:
                data["full_name"] = data["name"]
        return data


class LoginRequest(BaseModel):
    """Payload for user login."""

    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., min_length=1, description="Account password")


class RefreshTokenRequest(BaseModel):
    """Payload for token refresh and rotation."""

    refresh_token: str = Field(..., min_length=1, description="Valid JWT refresh token")


class ForgotPasswordRequest(BaseModel):
    """Payload for requesting password reset."""

    email: EmailStr = Field(..., description="User's registered email address")


class UserResponse(BaseModel):
    """Sanitized public user details."""

    id: str = Field(..., description="UUID of the user")
    full_name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    role: str = Field(..., description="User role, e.g. USER, ADMIN")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Account creation timestamp")

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Authentication tokens returned to the client."""

    access_token: str = Field(..., description="JWT access token (15m expiry)")
    refresh_token: str = Field(..., description="JWT refresh token (7d expiry)")
    token_type: str = Field(default="bearer", description="Token type, default 'bearer'")
    expires_in: int = Field(..., description="Access token lifetime in seconds (e.g. 900)")


class AuthResponseData(BaseModel):
    """Combined user profile and token package."""

    user: UserResponse
    tokens: TokenResponse


class ApiResponse(BaseModel, Generic[T]):
    """Standard API success response envelope matching rules.md 4.2."""

    success: bool = True
    data: T
    meta: dict[str, Any] | None = None


class MessageResponseData(BaseModel):
    """Generic message response."""

    message: str
