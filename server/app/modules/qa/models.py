"""Database model access helpers for AI Conversations."""

from typing import Any

from app.core.database import models


def get_ai_conversation_model() -> Any:
    """Returns the reflected AIConversation SQLAlchemy model class."""
    if models.AIConversation is None:
        raise RuntimeError("Database reflection has not been initialized. Call init_db() first.")
    return models.AIConversation
