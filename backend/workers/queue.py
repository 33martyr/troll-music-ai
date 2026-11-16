"""Job queues.

HTTP handlers only create a ``jobs`` row and enqueue its id; the work happens
in a worker. The queue is an interface so the in-process pool used for local
development can be replaced by a Redis-backed worker (Dramatiq or Celery)
without touching the handlers or the API.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

log = logging.getLogger(__name__)

RunJob = Callable[[str], None]


class JobQueue(Protocol):
    def enqueue(self, job_id: str) -> None: ...

    def shutdown(self) -> None: ...


class ThreadPoolJobQueue:
    """Runs jobs on a thread pool inside the API process.

    Fine for a single-machine install. Jobs do not survive a restart: anything
    unfinished is marked failed on the next startup.
    """

    def __init__(self, run_job: RunJob, workers: int = 2) -> None:
        self._run_job = run_job
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="troll-job")

    def enqueue(self, job_id: str) -> None:
        self._pool.submit(self._safe_run, job_id)

    def _safe_run(self, job_id: str) -> None:
        try:
            self._run_job(job_id)
        except Exception:  # the runner records failures; this is the last resort
            log.exception("Job %s crashed outside the runner", job_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class InlineJobQueue:
    """Runs the job before ``enqueue`` returns. For tests."""

    def __init__(self, run_job: RunJob) -> None:
        self._run_job = run_job

    def enqueue(self, job_id: str) -> None:
        self._run_job(job_id)

    def shutdown(self) -> None:
        return None
