"""Reflected models accessor for transcripts module."""

from typing import Any

from app.core.database import models


def get_transcript_segment_model() -> Any:
    """Returns reflected TranscriptSegment model class."""
    return models.TranscriptSegment


def get_speaker_model() -> Any:
    """Returns reflected Speaker model class."""
    return models.Speaker
