"""Users HTTP router handling authenticated user profile operations."""

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.auth_guard import get_current_user
from app.modules.auth.schemas import ApiResponse
from app.modules.users.schemas import UpdateUserProfileRequest, UserProfileResponse
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=ApiResponse[UserProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_my_profile(
    current_user: Any = Depends(get_current_user),
) -> ApiResponse[UserProfileResponse]:
    """Retrieves profile information for the authenticated user."""
    profile = UserService.get_profile(current_user)
    return ApiResponse(success=True, data=profile)


@router.patch(
    "/me",
    response_model=ApiResponse[UserProfileResponse],
    status_code=status.HTTP_200_OK,
    summary="Update current authenticated user profile",
)
async def update_my_profile(
    payload: UpdateUserProfileRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserProfileResponse]:
    """Updates profile attributes for the authenticated user."""
    profile = await UserService.update_profile(db, current_user, payload)
    return ApiResponse(success=True, data=profile)
