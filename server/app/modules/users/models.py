"""Reflected model accessor for users module."""

from typing import Any

from app.core.database import models


def get_user_model() -> Any:
    """Get the reflected User model class."""
    return models.User
