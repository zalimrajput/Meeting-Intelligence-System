"""Reflected SQLAlchemy model reference for authentication and users."""

from typing import Any

from app.core.database import models


def get_user_model() -> Any:
    """Returns the reflected SQLAlchemy User model class from Base.classes.users."""
    User = models.User
    if User is None:
        raise RuntimeError("Database reflection has not been initialized. Call init_db() first.")
    return User
