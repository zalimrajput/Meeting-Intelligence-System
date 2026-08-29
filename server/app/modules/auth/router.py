"""Authentication HTTP router handling registration, login, token refresh, and password recovery."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.middleware.rate_limiter import limiter
from app.modules.auth.schemas import (
    ApiResponse,
    AuthResponseData,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponseData,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=ApiResponse[AuthResponseData],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
@limiter.limit("20/minute")
async def register(
    request: Request,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AuthResponseData]:
    """Registers a new user, hashes password, and returns user profile with JWT tokens."""
    user, tokens = await AuthService.register_user(db, payload)
    return ApiResponse(
        success=True,
        data=AuthResponseData(user=user, tokens=tokens),
    )


@router.post(
    "/login",
    response_model=ApiResponse[AuthResponseData],
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and obtain JWT tokens",
)
@limiter.limit("20/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AuthResponseData]:
    """Authenticates credentials and returns user profile with new access and refresh tokens."""
    user, tokens = await AuthService.authenticate_user(db, payload)
    return ApiResponse(
        success=True,
        data=AuthResponseData(user=user, tokens=tokens),
    )


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponse],
    status_code=status.HTTP_200_OK,
    summary="Rotate JWT refresh token and issue new access token",
)
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenResponse]:
    """Validates refresh token and issues a new access token and rotated refresh token."""
    tokens = await AuthService.rotate_refresh_token(db, payload)
    return ApiResponse(
        success=True,
        data=tokens,
    )


@router.post(
    "/forgot-password",
    response_model=ApiResponse[MessageResponseData],
    status_code=status.HTTP_200_OK,
    summary="Request a password reset email",
)
@limiter.limit("10/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[MessageResponseData]:
    """Requests password reset instructions for the provided email address."""
    msg = await AuthService.request_password_reset(db, payload)
    return ApiResponse(
        success=True,
        data=MessageResponseData(message=msg),
    )
