"""Rate limiter configuration using Slowapi."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Global limiter instance keyed by client IP address
limiter: Limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.GENERAL_RATE_LIMIT],
    headers_enabled=False,
    storage_uri="memory://",
)
