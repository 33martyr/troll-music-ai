from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.deps import QueueDep, SessionDep, submit_job
from backend.core.errors import ApiError, not_found
from backend.models.schemas import JobOut
from backend.models.tables import Job, JobStatus, utcnow

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _load(session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise not_found("Job")
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(session: SessionDep, status: str | None = None, project_id: str | None = None, active: bool = False, limit: int = 30):
    """Newest first. ``active=true`` returns only queued and processing jobs."""
    query = select(Job).order_by(Job.created_at.desc()).limit(max(1, min(limit, 200)))
    if active:
        query = query.where(Job.status.in_(JobStatus.ACTIVE))
    elif status:
        query = query.where(Job.status.in_(status.split(",")))
    if project_id:
        query = query.where(Job.project_id == project_id)
    return list(session.scalars(query))


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: SessionDep):
    return _load(session, job_id)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, session: SessionDep):
    """Cancel a queued job at once; a running job stops at its next progress
    step (a model call already in flight is allowed to finish)."""
    job = _load(session, job_id)
    if job.status == JobStatus.QUEUED:
        job.status, job.stage, job.finished_at = JobStatus.CANCELLED, "Cancelled", utcnow()
    elif job.status == JobStatus.PROCESSING:
        job.cancel_requested = True
        job.stage = "Cancelling"
    else:
        raise ApiError(409, "not_cancellable", f"This job already {job.status}.")
    session.commit()
    session.refresh(job)
    return job


@router.post("/{job_id}/retry", response_model=JobOut, status_code=202)
def retry_job(job_id: str, session: SessionDep, queue: QueueDep):
    """Run a failed or cancelled job again as a new job with the same input."""
    job = _load(session, job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise ApiError(409, "not_retryable", "Only failed or cancelled jobs can be retried.")
    return submit_job(session, queue, kind=job.kind, project_id=job.project_id, params=dict(job.params), retry_of=job.id)
