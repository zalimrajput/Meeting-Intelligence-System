"""Database engine, async session factory, and automap reflection."""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.automap import automap_base

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create async engine with connection pooling and pre-ping
async_engine: AsyncEngine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
)

# Async session factory
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Alias for standard naming
async_session_maker = AsyncSessionLocal

# Shared MetaData and automap Base
metadata: MetaData = MetaData()
Base: Any = automap_base(metadata=metadata)


class ReflectedModels:
    """Registry holding references to SQLAlchemy automapped classes."""

    User: Any = None
    Meeting: Any = None
    TranscriptSegment: Any = None
    Speaker: Any = None
    Participant: Any = None
    MeetingFile: Any = None
    ProcessingJob: Any = None
    ActionItem: Any = None
    Decision: Any = None
    UnresolvedIssue: Any = None
    FollowUpItem: Any = None
    KeyPoint: Any = None
    Deadline: Any = None
    AIConversation: Any = None


models = ReflectedModels()


async def init_db() -> None:
    """Reflect existing database tables into automap Base classes asynchronously."""
    global Base, models
    if models.User is not None:
        return

    try:
        app_tables = [
            "users",
            "meetings",
            "meeting_files",
            "processing_jobs",
            "transcript_segments",
            "speakers",
            "participants",
            "action_items",
            "decisions",
            "unresolved_issues",
            "follow_up_items",
            "key_points",
            "deadlines",
            "ai_conversations",
        ]
        async with async_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: metadata.reflect(bind=sync_conn, only=app_tables, schema="public"))

        Base = automap_base(metadata=metadata)
        Base.prepare()

        # Map reflected table classes to readable model names
        table_classes = Base.classes

        models.User = table_classes.get("users")
        models.Meeting = table_classes.get("meetings")
        models.TranscriptSegment = table_classes.get("transcript_segments")
        models.Speaker = table_classes.get("speakers")
        models.Participant = table_classes.get("participants")
        models.MeetingFile = table_classes.get("meeting_files")
        models.ProcessingJob = table_classes.get("processing_jobs")
        models.ActionItem = table_classes.get("action_items")
        models.Decision = table_classes.get("decisions")
        models.UnresolvedIssue = table_classes.get("unresolved_issues")
        models.FollowUpItem = table_classes.get("follow_up_items")
        models.KeyPoint = table_classes.get("key_points")
        models.Deadline = table_classes.get("deadlines")
        models.AIConversation = table_classes.get("ai_conversations")

        logger.info(
            "Successfully reflected %d database tables: %s",
            len(metadata.tables),
            list(metadata.tables.keys()),
        )
    except Exception as exc:
        logger.warning("Failed to reflect database tables (tables may not exist yet): %s", str(exc))
        logger.warning("Run 'alembic upgrade head' to create database tables.")
        # Don't crash - let the app start even without tables
        # Tables will be reflected on next request after migrations are run


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency providing an async database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
