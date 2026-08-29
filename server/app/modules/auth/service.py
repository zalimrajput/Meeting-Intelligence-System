"""Authentication business logic service (isolated from HTTP/FastAPI request contexts)."""

import logging
import uuid
from datetime import UTC, datetime

from jose import ExpiredSignatureError, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.middleware.error_handler import AppError
from app.modules.auth.models import get_user_model
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)


class AuthService:
    """Service class handling all authentication and token lifecycle operations."""

    @staticmethod
    async def register_user(
        db: AsyncSession,
        payload: RegisterRequest,
    ) -> tuple[UserResponse, TokenResponse]:
        """
        Registers a new user, hashes password, saves record in DB, and issues tokens.
        """
        User = get_user_model()
        normalized_email = payload.email.strip().lower()

        # Check if email is already registered
        stmt = select(User).where(User.email == normalized_email)
        result = await db.execute(stmt)
        existing_user = result.scalars().first()

        if existing_user:
            logger.info("Registration failed: user with email %s already exists.", normalized_email)
            raise AppError(
                status_code=409,
                code="USER_ALREADY_EXISTS",
                message="A user with this email address already exists.",
            )

        now = datetime.now(UTC)
        user_id = uuid.uuid4()
        hashed_pwd = hash_password(payload.password)

        new_user = User(
            id=user_id,
            full_name=payload.full_name.strip(),
            email=normalized_email,
            password_hash=hashed_pwd,
            role="member",
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        user_response = UserResponse(
            id=str(new_user.id),
            full_name=new_user.full_name,
            email=new_user.email,
            role=new_user.role,
            is_active=new_user.is_active,
            created_at=new_user.created_at,
        )

        access_token, expires_in = create_access_token(
            user_id=str(new_user.id),
            email=new_user.email,
            role=new_user.role,
        )
        refresh_token = create_refresh_token(user_id=str(new_user.id))

        tokens = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

        logger.info(
            "Successfully registered user id=%s email=%s", str(new_user.id), normalized_email
        )
        return user_response, tokens

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        payload: LoginRequest,
    ) -> tuple[UserResponse, TokenResponse]:
        """
        Validates user credentials and issues access & refresh tokens upon success.
        """
        User = get_user_model()
        normalized_email = payload.email.strip().lower()

        stmt = select(User).where(User.email == normalized_email)
        result = await db.execute(stmt)
        user = result.scalars().first()

        if not user or not verify_password(payload.password, user.password_hash):
            logger.warning("Failed login attempt for email: %s", normalized_email)
            raise AppError(
                status_code=401,
                code="INVALID_CREDENTIALS",
                message="Invalid email or password.",
            )

        if not getattr(user, "is_active", True):
            logger.warning("Inactive account login attempt: user_id=%s", str(user.id))
            raise AppError(
                status_code=403,
                code="ACCOUNT_INACTIVE",
                message="This account has been deactivated. Please contact support.",
            )

        user_response = UserResponse(
            id=str(user.id),
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )

        access_token, expires_in = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
        )
        refresh_token = create_refresh_token(user_id=str(user.id))

        tokens = TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

        logger.info("Successful login for user_id=%s email=%s", str(user.id), normalized_email)
        return user_response, tokens

    @staticmethod
    async def rotate_refresh_token(
        db: AsyncSession,
        payload: RefreshTokenRequest,
    ) -> TokenResponse:
        """
        Verifies refresh token validity, validates active user, and issues a rotated pair of tokens.
        """
        try:
            token_payload = decode_token(payload.refresh_token)
        except ExpiredSignatureError:
            raise AppError(
                status_code=401,
                code="TOKEN_EXPIRED",
                message="Refresh token has expired. Please log in again.",
            ) from None
        except JWTError:
            raise AppError(
                status_code=401,
                code="INVALID_TOKEN",
                message="Invalid refresh token.",
            ) from None

        if token_payload.get("type") != "refresh":
            raise AppError(
                status_code=401,
                code="INVALID_TOKEN_TYPE",
                message="Invalid token type. Expected a refresh token.",
            )

        user_id_str = token_payload.get("sub")
        if not user_id_str:
            raise AppError(
                status_code=401,
                code="INVALID_TOKEN",
                message="Malformed refresh token.",
            )

        try:
            user_uuid = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            raise AppError(
                status_code=401,
                code="INVALID_TOKEN",
                message="Invalid user identifier in refresh token.",
            ) from None

        User = get_user_model()
        stmt = select(User).where(User.id == user_uuid)
        result = await db.execute(stmt)
        user = result.scalars().first()

        if not user:
            raise AppError(
                status_code=401,
                code="USER_NOT_FOUND",
                message="User associated with this refresh token no longer exists.",
            )

        if not getattr(user, "is_active", True):
            raise AppError(
                status_code=403,
                code="ACCOUNT_INACTIVE",
                message="This user account has been deactivated.",
            )

        # Issue new rotated tokens
        new_access_token, expires_in = create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
        )
        new_refresh_token = create_refresh_token(user_id=str(user.id))

        logger.info("Successfully rotated refresh token for user_id=%s", str(user.id))
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

    @staticmethod
    async def request_password_reset(
        db: AsyncSession,
        payload: ForgotPasswordRequest,
    ) -> str:
        """
        Initiates password reset process for the specified email.
        Always returns generic message to prevent email enumeration.
        """
        User = get_user_model()
        normalized_email = payload.email.strip().lower()

        stmt = select(User).where(User.email == normalized_email)
        result = await db.execute(stmt)
        user = result.scalars().first()

        if user:
            logger.info("Password reset requested for registered email: %s", normalized_email)
        else:
            logger.info("Password reset requested for non-existing email: %s", normalized_email)

        return "If an account with that email exists, password reset instructions have been sent."
