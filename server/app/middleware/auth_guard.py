"""Authentication guard and user context dependencies."""

import uuid
from typing import Any

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, models
from app.core.security import decode_token
from app.middleware.error_handler import AppError

# HTTP Bearer scheme (auto_error=False so we can raise our structured AppError)
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    FastAPI dependency that extracts, verifies the JWT Bearer access token,
    and returns the authenticated active user record from PostgreSQL.
    Supports both Authorization header and query parameter ?token= for media streaming.
    """
    token: str | None = None
    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
        while token.lower().startswith("bearer "):
            token = token[7:].strip()
        token = token.strip("\"'")
    elif request.query_params.get("token"):
        token = request.query_params.get("token", "").strip()

    if not token:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message="Authentication credentials were not provided in Authorization header or query parameter.",
        )

    try:
        payload = decode_token(token)
    except ExpiredSignatureError:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="TOKEN_EXPIRED",
            message="Access token has expired. Please refresh your session.",
        ) from None
    except JWTError:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_TOKEN",
            message="Invalid authentication token.",
        ) from None

    # Validate token type
    if payload.get("type") != "access":
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_TOKEN_TYPE",
            message="Invalid token type. Expected an access token.",
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_TOKEN",
            message="Token payload is missing user subject identifier.",
        )

    try:
        user_uuid = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_TOKEN",
            message="Invalid user identifier in token.",
        ) from None

    User = models.User
    if User is None:
        raise AppError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Database models are not initialized.",
        )

    stmt = select(User).where(User.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise AppError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="USER_NOT_FOUND",
            message="The user account associated with this token no longer exists.",
        )

    if not getattr(user, "is_active", True):
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ACCOUNT_INACTIVE",
            message="This user account has been deactivated.",
        )

    return user


def enforce_user_ownership(resource_owner_id: str | uuid.UUID, current_user: Any) -> None:
    """
    Enforces that the current authenticated user owns the accessed resource.
    Raises AppError 403 FORBIDDEN if user is not the owner.
    """
    current_user_id = str(getattr(current_user, "id", ""))
    if str(resource_owner_id) != current_user_id:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN_RESOURCE",
            message="You do not have permission to access this resource.",
        )
