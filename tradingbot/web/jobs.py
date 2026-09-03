"""Background jobs for the dashboard.

Some of what the site offers takes minutes — a walk-forward sweep runs hundreds
of backtests, a carry scan makes a network call per symbol. Those cannot be a
plain request/response without the browser timing out, so they run on a worker
thread and the page polls for progress.

Deliberately in-process and in-memory: this is a local tool for one operator, and
a Redis dependency would buy nothing. Jobs die with the server, which is the
correct behaviour for something you started by running a command in a terminal.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

log = logging.getLogger(__name__)

#: Finished jobs are kept this long so a page can still collect the result.
RETENTION_SECONDS = 30 * 60
MAX_JOBS = 100


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (JobState.DONE, JobState.FAILED, JobState.CANCELLED)


class Cancelled(Exception):
    """Raised inside a job when the operator asked it to stop."""


@dataclass
class Job:
    id: str
    kind: str
    #: What the job is about, for a listing: "sma_cross · BTC/USDT 1h".
    label: str = ""
    #: The request that started it, so a page reopening the job can put the
    #: same setup back in its form and hand it on to the next step.
    request: dict | None = None
    state: JobState = JobState.QUEUED
    progress: float = 0.0
    message: str = ""
    result: dict | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def as_dict(self, include_result: bool = True) -> dict:
        """Serialise for the API.

        The job list is polled every few seconds by every open tab, and a
        walk-forward result carries an equity curve and a trade list. Listings
        therefore carry a summary only; the per-job endpoint has the result.
        """
        payload = {
            "id": self.id,
            "kind": self.kind,
            "state": self.state.value,
            "progress": round(self.progress, 4),
            "message": self.message,
            "label": self.label,
            "error": self.error,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "created_at": self.created_at.isoformat(),
            "has_result": self.result is not None,
        }
        if include_result:
            payload["result"] = self.result
            payload["request"] = self.request
        return payload


class JobContext:
    """Handed to a job so it can report progress and notice cancellation."""

    def __init__(self, job: Job) -> None:
        self._job = job

    def progress(self, fraction: float, message: str = "") -> None:
        """Report how far along the work is. Also the cancellation checkpoint."""
        self.raise_if_cancelled()
        self._job.progress = max(0.0, min(1.0, fraction))
        if message:
            self._job.message = message

    def raise_if_cancelled(self) -> None:
        if self._job._cancel.is_set():
            raise Cancelled()

    @property
    def cancelled(self) -> bool:
        return self._job._cancel.is_set()


class JobRunner:
    """Runs jobs on worker threads and keeps their results briefly."""

    def __init__(self, retention_seconds: int = RETENTION_SECONDS, max_jobs: int = MAX_JOBS) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.retention_seconds = retention_seconds
        self.max_jobs = max_jobs

    # ------------------------------------------------------------------
    def submit(
        self, kind: str, fn: Callable[[JobContext], dict], label: str = "", request: dict | None = None
    ) -> Job:
        """Start `fn` on a worker thread and return its job immediately."""
        self._evict()
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, label=label, request=request)
        with self._lock:
            self._jobs[job.id] = job

        thread = threading.Thread(target=self._run, args=(job, fn), daemon=True, name=f"job-{kind}")
        thread.start()
        return job

    def _run(self, job: Job, fn: Callable[[JobContext], dict]) -> None:
        job.state = JobState.RUNNING
        job.started_at = datetime.now(timezone.utc)
        try:
            job.result = fn(JobContext(job))
            job.state = JobState.DONE
            job.progress = 1.0
            job.message = job.message or "complete"
        except Cancelled:
            job.state = JobState.CANCELLED
            job.message = "cancelled"
        except Exception as exc:  # noqa: BLE001 - a failed job must not kill the server
            job.state = JobState.FAILED
            job.error = str(exc) or exc.__class__.__name__
            log.error("job %s (%s) failed: %s", job.id, job.kind, exc)
            log.debug("%s", traceback.format_exc())
        finally:
            job.finished_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """Ask a job to stop. It stops at its next progress checkpoint."""
        job = self.get(job_id)
        if job is None or job.state.finished:
            return False
        job._cancel.set()
        job.message = "cancelling…"
        return True

    def list_jobs(self, limit: int = 20) -> list[Job]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def _evict(self) -> None:
        """Drop finished jobs that are old, and cap total memory use."""
        now = time.time()
        with self._lock:
            stale = [
                job_id for job_id, job in self._jobs.items()
                if job.state.finished
                and job.finished_at
                and now - job.finished_at.timestamp() > self.retention_seconds
            ]
            for job_id in stale:
                del self._jobs[job_id]

            if len(self._jobs) > self.max_jobs:
                # Oldest finished jobs go first; running ones are never evicted.
                finished = sorted(
                    (j for j in self._jobs.values() if j.state.finished),
                    key=lambda j: j.created_at,
                )
                for job in finished[: len(self._jobs) - self.max_jobs]:
                    self._jobs.pop(job.id, None)

    def shutdown(self) -> None:
        """Signal every running job to stop."""
        for job in self.list_jobs(limit=self.max_jobs):
            if not job.state.finished:
                job._cancel.set()
