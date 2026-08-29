"""Reflected models accessor for insights module."""

from typing import Any

from app.core.database import models


def get_action_item_model() -> Any:
    """Returns reflected ActionItem model."""
    return models.ActionItem


def get_decision_model() -> Any:
    """Returns reflected Decision model."""
    return models.Decision


def get_key_point_model() -> Any:
    """Returns reflected KeyPoint model."""
    return models.KeyPoint


def get_unresolved_issue_model() -> Any:
    """Returns reflected UnresolvedIssue model."""
    return models.UnresolvedIssue
