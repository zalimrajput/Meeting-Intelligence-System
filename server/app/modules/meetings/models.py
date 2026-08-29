"""Reflected models accessor for meetings module."""

from typing import Any

from app.core.database import models


def get_meeting_model() -> Any:
    """Returns reflected Meeting model class."""
    return models.Meeting


def get_meeting_file_model() -> Any:
    """Returns reflected MeetingFile model class."""
    return models.MeetingFile


def get_processing_job_model() -> Any:
    """Returns reflected ProcessingJob model class."""
    return models.ProcessingJob
