"""MeetingMind Windows-Compatible Background Worker Runner.

Provides a robust runner for arq background jobs on Windows OS without signal handler
crashes (avoiding NotImplementedError on ProactorEventLoop), adds Redis worker heartbeat,
and handles auto-restart on unhandled exceptions.
"""

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.database import init_db
from app.worker import WorkerSettings, process_meeting

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("meetingmind.worker_runner")

HEARTBEAT_KEY = "meetingmind:worker:heartbeat"
HEARTBEAT_INTERVAL = 5.0  # seconds

try:
    from arq.connections import RedisSettings, create_pool
    from arq.worker import Worker
except ImportError:
    Worker = None
    create_pool = None
    RedisSettings = None


class WindowsCompatibleWorker(Worker if Worker else object):
    """
    Subclass of arq.Worker that overrides signal handler registration
    to prevent NotImplementedError on Windows asyncio event loops.
    """

    def _add_signal_handler(self, sig: Any, callback: Any) -> None:
        """Silently pass signal registration on Windows systems."""
        pass


async def heartbeat_loop(redis_pool: Any) -> None:
    """Continuously writes worker heartbeat timestamp to Redis."""
    while True:
        try:
            now_iso = datetime.now(UTC).isoformat()
            await redis_pool.set(HEARTBEAT_KEY, now_iso, ex=30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug("Heartbeat ping failed: %s", e)
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def run_worker_instance() -> None:
    """Runs a single instance of the background worker with heartbeat."""
    logger.info("Initializing MeetingMind background worker...")
    await init_db()

    # Parse Redis settings from application config
    redis_url = settings.REDIS_URL
    redis_settings = RedisSettings.from_dsn(redis_url)

    if create_pool is None or WindowsCompatibleWorker is None:
        logger.warning(
            "arq or RedisSettings not available. Running fallback worker loop."
        )
        while True:
            await asyncio.sleep(5)
        return

    # Connect to Redis
    redis_pool = await create_pool(redis_settings)
    logger.info("Connected to Redis for worker at %s", settings.REDIS_URL)

    # Initialize heartbeat task
    heartbeat_task = asyncio.create_task(heartbeat_loop(redis_pool))

    try:
        worker = WindowsCompatibleWorker(
            functions=[process_meeting],
            redis_pool=redis_pool,
            on_startup=WorkerSettings.on_startup,
            on_shutdown=WorkerSettings.on_shutdown,
            max_tries=WorkerSettings.max_tries,
            job_timeout=WorkerSettings.job_timeout,
            handle_signals=False,
            burst=False,
            poll_delay=0.5,
        )
        logger.info("MeetingMind Worker started successfully. Listening for jobs...")
        await worker.main()
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        try:
            if hasattr(redis_pool, "aclose"):
                await redis_pool.aclose()
            elif hasattr(redis_pool, "close"):
                await redis_pool.close()
        except Exception:
            pass
        logger.info("Worker instance terminated cleanly.")


def main() -> None:
    """Main process entry point with auto-restart supervisor loop."""
    logger.info(
        "Starting MeetingMind Windows-compatible Worker Service (PID: %d)...",
        os.getpid(),
    )

    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception as e:
            logger.debug("Could not set WindowsSelectorEventLoopPolicy: %s", e)

    while True:
        try:
            asyncio.run(run_worker_instance())
            break
        except KeyboardInterrupt:
            logger.info("Worker service received SIGINT / KeyboardInterrupt. Shutting down...")
            break
        except Exception as exc:
            logger.error(
                "Worker crashed with unexpected error: %s. Auto-restarting in 3s...",
                exc,
                exc_info=True,
            )
            import time
            time.sleep(3)


if __name__ == "__main__":
    main()
