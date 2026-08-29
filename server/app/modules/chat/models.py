"""Reflected models accessor for chat module."""

from typing import Any

from app.core.database import models


def get_ai_conversation_model() -> Any:
    """Returns reflected AIConversation model."""
    return models.AIConversation
