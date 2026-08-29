"""User schemas for profile queries and updates."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserProfileResponse(BaseModel):
    """Authenticated user profile representation."""

    id: str = Field(..., description="User UUID")
    full_name: str = Field(..., description="Full Name")
    email: str = Field(..., description="Email address")
    role: str = Field(..., description="Role")
    is_active: bool = Field(..., description="Active status")
    created_at: datetime = Field(..., description="Registration timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True)


class UpdateUserProfileRequest(BaseModel):
    """Payload to update profile information."""

    full_name: str | None = Field(None, min_length=2, max_length=150)
