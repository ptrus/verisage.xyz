"""Huey task queue configuration and tasks."""

import asyncio
import logging
import os
from pathlib import Path

from huey import SqliteHuey, crontab

from src.config import settings
from src.job_store import job_store
from src.models import JobStatus
from src.oracle import oracle
from src.signing import signing_service

# Configure logging.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s:%(name)s:%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Get data directory from environment or use current directory.
DATA_DIR = os.getenv("DATA_DIR", ".")
# Ensure data directory exists before creating database.
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
huey_db_path = Path(DATA_DIR) / "huey.db"

# Initialize Huey with SQLite storage.
huey = SqliteHuey(
    filename=str(huey_db_path),
    immediate=False,
    results=False,
    name="verisage-queue",
)

logger = logging.getLogger(__name__)


@huey.on_startup()
def initialize_worker():
    """Initialize worker on startup."""
    logger.info("Initializing worker...")

    # Initialize ROFL signing service (production only).
    asyncio.run(signing_service.initialize())

    logger.info("Worker initialization complete")


@huey.task(retries=2, retry_delay=60)
def process_oracle_query(job_id: str, query: str):
    """Process an oracle query in the background.

    Retries up to 2 times with 60 second delay between attempts.

    Args:
        job_id: The job identifier
        query: The dispute question to resolve
    """
    import asyncio
    import time

    start_time = time.time()
    logger.info(f"Processing job {job_id}: {query}")

    try:
        # Update status to processing.
        job_store.update_job_status(job_id, JobStatus.PROCESSING)

        # Run async oracle resolution via asyncio.run because Huey tasks are synchronous.
        result = asyncio.run(oracle.resolve_dispute(query))

        # Sign the result (production only).
        signed_result = signing_service.sign_result(result)

        # Store the signed result.
        job_store.update_job_result(job_id, signed_result)

        elapsed_time = time.time() - start_time
        logger.info(
            f"Job {job_id} completed successfully in {elapsed_time:.2f}s "
            f"(decision: {result.final_decision.value}, confidence: {result.final_confidence:.2f})"
        )

    except Exception as e:
        # Handle any errors.
        elapsed_time = time.time() - start_time
        error_msg = f"Failed to process query: {str(e)}"
        logger.error(f"Job {job_id} failed after {elapsed_time:.2f}s: {error_msg}", exc_info=True)
        job_store.update_job_error(job_id, error_msg)


@huey.periodic_task(crontab(hour="*/6"))  # Run every 6 hours.
def cleanup_old_jobs():
    """Periodic task to keep only the latest N jobs (configured via JOB_RETENTION_COUNT)."""
    deleted = job_store.cleanup_keep_latest(keep_count=settings.job_retention_count)
    if deleted > 0:
        logger.info(
            f"Cleaned up {deleted} old jobs (keeping latest {settings.job_retention_count})"
        )
