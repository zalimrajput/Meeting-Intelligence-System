"""User service handling profile management and queries."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.schemas import UpdateUserProfileRequest, UserProfileResponse


class UserService:
    """Service class for user queries and updates."""

    @staticmethod
    def get_profile(current_user: Any) -> UserProfileResponse:
        """Returns the profile response model from current authenticated user."""
        return UserProfileResponse(
            id=str(current_user.id),
            full_name=current_user.full_name,
            email=current_user.email,
            role=current_user.role,
            is_active=current_user.is_active,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at,
        )

    @staticmethod
    async def update_profile(
        db: AsyncSession,
        current_user: Any,
        payload: UpdateUserProfileRequest,
    ) -> UserProfileResponse:
        """Updates user profile information."""
        if payload.full_name is not None:
            current_user.full_name = payload.full_name.strip()

        current_user.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(current_user)

        return UserProfileResponse(
            id=str(current_user.id),
            full_name=current_user.full_name,
            email=current_user.email,
            role=current_user.role,
            is_active=current_user.is_active,
            created_at=current_user.created_at,
            updated_at=current_user.updated_at,
        )
