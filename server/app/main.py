"""Main FastAPI application entrypoint for MeetingMind AI Meeting Intelligence System."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import async_engine, init_db
from app.middleware.error_handler import register_error_handlers
from app.middleware.rate_limiter import limiter
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import router as auth_router
from app.modules.auth.schemas import ApiResponse
from app.modules.chat.router import router as chat_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.export.router import router as export_router
from app.modules.insights.router import router as insights_router
from app.modules.meetings.router import router as meetings_router
from app.modules.transcripts.router import router as transcripts_router
from app.modules.users.router import router as users_router
from app.services.media_preprocessor import is_ffmpeg_available
from app.services.queue import close_redis_pool

# Configure structured application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("meetingmind.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager to handle startup reflection and graceful shutdown."""
    logger.info("Initializing MeetingMind FastAPI application...")
    logger.info("Environment: %s", settings.ENVIRONMENT)

    # Introspect existing PostgreSQL schema via automap
    try:
        await init_db()
        logger.info("Database table reflection complete.")
    except Exception as exc:
        logger.warning("Database reflection failed (tables may not exist yet): %s", str(exc))
        logger.warning("The API will start but some features may not work until migrations are run.")

    # Probe FFmpeg availability for media preprocessing
    if is_ffmpeg_available():
        logger.info("FFmpeg is available in system PATH for audio extraction.")
    else:
        logger.warning(
            "FFmpeg executable not detected in PATH. Video audio extraction will require FFmpeg."
        )

    # Validate required configuration keys
    if settings.ENVIRONMENT != "test":
        settings.validate_required_keys()

    yield

    logger.info("Shutting down MeetingMind API server...")
    await close_redis_pool()
    await async_engine.dispose()
    logger.info("Database connections closed.")


# Initialize FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for MeetingMind AI Meeting Intelligence System",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Attach rate limiter to application state
app.state.limiter = limiter

# Register global exception handlers producing uniform API response envelopes
register_error_handlers(app)

# Configure CORS middleware (whitelisting frontend origin and production placeholder)
origins = [
    settings.FRONTEND_URL,
    settings.PRODUCTION_FRONTEND_URL,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
# Remove duplicates
origins = list(dict.fromkeys([o.rstrip("/") for o in origins if o]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 Routers
api_v1_prefix = settings.API_V1_PREFIX

app.include_router(auth_router, prefix=api_v1_prefix)
app.include_router(users_router, prefix=api_v1_prefix)
app.include_router(meetings_router, prefix=api_v1_prefix)
app.include_router(transcripts_router, prefix=api_v1_prefix)
app.include_router(insights_router, prefix=api_v1_prefix)
app.include_router(chat_router, prefix=api_v1_prefix)
app.include_router(dashboard_router, prefix=api_v1_prefix)
app.include_router(export_router, prefix=api_v1_prefix)
app.include_router(admin_router, prefix=api_v1_prefix)




@app.get(
    "/",
    tags=["System"],
    summary="Root API Landing",
    include_in_schema=False,
)
async def root():
    """Root endpoint welcoming visitors and directing to interactive documentation."""
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "api_v1": settings.API_V1_PREFIX,
    }


@app.get(
    f"{api_v1_prefix}/health",
    response_model=ApiResponse[dict[str, str]],
    status_code=status.HTTP_200_OK,
    tags=["System"],
    summary="System health check",
)
async def health_check() -> ApiResponse[dict[str, str]]:
    """Health check endpoint to verify API server status and connectivity."""
    return ApiResponse(
        success=True,
        data={
            "status": "healthy",
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        },
    )

