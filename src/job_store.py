"""SQLite-based job storage for oracle queries."""

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.models import JobStatus, OracleResult


class JobStore:
    """Manages job storage in SQLite database."""

    def __init__(self, db_path: str | None = None, timeout: float = 5.0):
        """Initialize job store with SQLite database.

        Args:
            db_path: Path to SQLite database file (uses DATA_DIR/jobs.db if not provided)
            timeout: Seconds to wait for database locks before failing
        """
        if db_path is None:
            data_dir = os.getenv("DATA_DIR", ".")
            # Ensure data directory exists before creating database.
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            db_path = str(Path(data_dir) / "jobs.db")

        self.db_path = db_path
        self.timeout = timeout
        self._init_db()

    @contextmanager
    def _cursor(self, *, row_factory=None):
        """Context manager that yields a SQLite cursor with standard settings."""
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        if row_factory is not None:
            conn.row_factory = row_factory

        cursor = conn.cursor()

        try:
            yield cursor
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema if it doesn't exist."""
        with self._cursor() as cursor:
            # Improve concurrent access between API and worker processes.
            cursor.execute("PRAGMA journal_mode=WAL")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY CHECK(length(id) = 36),
                    status TEXT NOT NULL,
                    query TEXT NOT NULL CHECK(length(query) <= 2048),
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    payer_address TEXT,
                    tx_hash TEXT,
                    network TEXT
                )
            """)

            # Create index on created_at for efficient cleanup queries.
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at)
            """)

    def create_job(
        self,
        query: str,
        payer_address: str | None = None,
        tx_hash: str | None = None,
        network: str | None = None,
    ) -> tuple[str, datetime]:
        """Create a new job entry.

        Args:
            query: The oracle query to process
            payer_address: Address of the payer (if payment was made)
            tx_hash: Transaction hash of the payment
            network: Network the payment was made on

        Returns:
            Tuple of (job_id, created_at timestamp)
        """
        job_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)

        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO jobs (id, status, query, created_at, payer_address, tx_hash, network)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    JobStatus.PENDING.value,
                    query,
                    created_at.isoformat(),
                    payer_address,
                    tx_hash,
                    network,
                ),
            )

        return job_id, created_at

    def get_job(self, job_id: str) -> dict | None:
        """Get job details by ID.

        Args:
            job_id: The job identifier

        Returns:
            Job data dict or None if not found
        """
        with self._cursor(row_factory=sqlite3.Row) as cursor:
            cursor.execute(
                """
                SELECT id, status, query, result_json, error, created_at, completed_at,
                       payer_address, tx_hash, network
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row["id"],
            "status": row["status"],
            "query": row["query"],
            "result_json": row["result_json"],
            "error": row["error"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "payer_address": row["payer_address"],
            "tx_hash": row["tx_hash"],
            "network": row["network"],
        }

    def update_job_status(self, job_id: str, status: JobStatus):
        """Update job status.

        Args:
            job_id: The job identifier
            status: New status to set
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE jobs
                SET status = ?
                WHERE id = ?
                """,
                (status.value, job_id),
            )

    def update_job_result(self, job_id: str, result: OracleResult):
        """Update job with successful result.

        Args:
            job_id: The job identifier
            result: The oracle result to store
        """
        completed_at = datetime.now(UTC)
        result_json = result.model_dump_json()

        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE jobs
                SET status = ?, result_json = ?, completed_at = ?
                WHERE id = ?
                """,
                (JobStatus.COMPLETED.value, result_json, completed_at.isoformat(), job_id),
            )

    def update_job_error(self, job_id: str, error: str):
        """Update job with error.

        Args:
            job_id: The job identifier
            error: Error message
        """
        completed_at = datetime.now(UTC)

        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE jobs
                SET status = ?, error = ?, completed_at = ?
                WHERE id = ?
                """,
                (JobStatus.FAILED.value, error, completed_at.isoformat(), job_id),
            )

    def cleanup_old_jobs(self, hours: int = 1) -> int:
        """Delete jobs older than specified hours.

        Args:
            hours: Age threshold in hours (default: 1)

        Returns:
            Number of jobs deleted
        """
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM jobs
                WHERE created_at < ?
                """,
                (cutoff.isoformat(),),
            )

            deleted = cursor.rowcount

        return deleted

    def cleanup_keep_latest(self, keep_count: int = 1000) -> int:
        """Delete old jobs, keeping only the latest N jobs.

        Args:
            keep_count: Number of most recent jobs to keep (default: 1000)

        Returns:
            Number of jobs deleted
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM jobs
                WHERE id NOT IN (
                    SELECT id FROM jobs
                    ORDER BY created_at DESC
                    LIMIT ?
                )
                """,
                (keep_count,),
            )

            deleted = cursor.rowcount

        return deleted

    def get_recent_completed_jobs(
        self, limit: int = 5, exclude_uncertain: bool = True
    ) -> list[dict]:
        """Get recently completed jobs.

        Args:
            limit: Maximum number of jobs to return (default: 5)
            exclude_uncertain: Exclude jobs with uncertain final_decision (default: True)

        Returns:
            List of job data dictionaries, most recent first
        """
        with self._cursor(row_factory=sqlite3.Row) as cursor:
            if exclude_uncertain:
                # Filter out uncertain results using JSON extraction
                cursor.execute(
                    """
                    SELECT id, status, query, result_json, error, created_at, completed_at,
                           payer_address, tx_hash, network
                    FROM jobs
                    WHERE status = ?
                    AND (result_json IS NULL OR json_extract(result_json, '$.final_decision') != 'uncertain')
                    ORDER BY completed_at DESC
                    LIMIT ?
                    """,
                    (JobStatus.COMPLETED.value, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, status, query, result_json, error, created_at, completed_at,
                           payer_address, tx_hash, network
                    FROM jobs
                    WHERE status = ?
                    ORDER BY completed_at DESC
                    LIMIT ?
                    """,
                    (JobStatus.COMPLETED.value, limit),
                )

            rows = cursor.fetchall()

        return [
            {
                "id": row["id"],
                "status": row["status"],
                "query": row["query"],
                "result_json": row["result_json"],
                "error": row["error"],
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
                "payer_address": row["payer_address"],
                "tx_hash": row["tx_hash"],
                "network": row["network"],
            }
            for row in rows
        ]

    def get_recent_job_stats(self, limit: int = 10) -> dict:
        """Get statistics about recently completed jobs.

        Args:
            limit: Number of recent jobs to analyze (default: 10)

        Returns:
            Dict with 'total' and 'failed' counts
        """
        with self._cursor(row_factory=sqlite3.Row) as cursor:
            cursor.execute(
                """
                SELECT status
                FROM jobs
                WHERE status IN (?, ?)
                ORDER BY completed_at DESC
                LIMIT ?
                """,
                (JobStatus.COMPLETED.value, JobStatus.FAILED.value, limit),
            )

            rows = cursor.fetchall()

        total = len(rows)
        failed = sum(1 for row in rows if row["status"] == JobStatus.FAILED.value)

        return {"total": total, "failed": failed}

    def get_queued_job_count(self) -> int:
        """Get count of jobs that are currently queued or processing.

        Returns:
            Number of jobs in PENDING or PROCESSING status
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM jobs
                WHERE status IN (?, ?)
                """,
                (JobStatus.PENDING.value, JobStatus.PROCESSING.value),
            )

            count = cursor.fetchone()[0]

        return count


# Global job store instance.
job_store = JobStore()
