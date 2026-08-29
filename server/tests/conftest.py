"""Test configuration and fixtures."""

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_engine, async_session_maker, init_db, metadata

# Enforce test environment mode for all pytest executions
settings.ENVIRONMENT = "test"


TABLES_TO_CLEAN = [
    "ai_conversations",
    "deadlines",
    "follow_up_items",
    "unresolved_issues",
    "decisions",
    "action_items",
    "key_points",
    "transcript_segments",
    "speakers",
    "participants",
    "meeting_files",
    "processing_jobs",
    "meetings",
    "users",
]


@pytest.fixture(autouse=True, scope="function")
async def clean_database():
    """Clean database tables before each test."""
    await init_db()
    async with async_session_maker() as session:
        # Use DELETE instead of TRUNCATE for better transactional behavior
        for table_name in TABLES_TO_CLEAN:
            result = await session.execute(text(f'DELETE FROM "{table_name}"'))
            print(f"DELETE {table_name}: {result.rowcount} rows affected")
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Initialize database reflection once per session."""
    await init_db()
    yield
    await async_engine.dispose()