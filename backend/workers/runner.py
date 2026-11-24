"""Executes one job: loads it, runs its handler, records the outcome."""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from backend.core.storage import Storage
from backend.models.tables import Asset, AssetLink, Job, JobStatus, utcnow
from backend.services.assets import create_asset
from backend.services.providers import ProviderManager
from troll_music_ai import TrollMusicError
from troll_music_ai.providers import Provider, ProviderInfo, TextGenerationProvider

log = logging.getLogger(__name__)


class JobCancelled(Exception):
    """Raised inside a handler when the user cancelled the job."""


@dataclass
class JobContext:
    session: Session
    job: Job
    providers: ProviderManager
    storage: Storage
    workdir: Path
    outputs: list[str] = field(default_factory=list)

    @property
    def params(self) -> dict[str, Any]:
        return self.job.params

    @property
    def text_provider(self) -> TextGenerationProvider | None:
        return self.providers.get("text")  # type: ignore[return-value]

    def progress(self, fraction: float, stage: str) -> None:
        """Record real progress. Also the point where cancellation takes effect."""
        self.session.refresh(self.job, ["cancel_requested"])
        if self.job.cancel_requested:
            raise JobCancelled()
        self.job.progress = max(0.0, min(1.0, fraction))
        self.job.stage = stage[:120]
        self.session.commit()

    def using(self, provider: Provider) -> ProviderInfo:
        """Record which provider and model this job runs on."""
        info = provider.info
        self.job.provider, self.job.model = info.name, info.model
        self.session.commit()
        return info

    def asset(self, asset_id: str | None, kind: str | tuple[str, ...] | None = None) -> Asset:
        asset = self.session.get(Asset, asset_id) if asset_id else None
        kinds = (kind,) if isinstance(kind, str) else kind
        if asset is None or (kinds and asset.kind not in kinds):
            raise TrollMusicError(f"The {kinds[0] if kinds else 'asset'} this job refers to no longer exists.")
        return asset

    def file_of(self, asset: Asset) -> Path:
        if not asset.storage_key or not self.storage.exists(asset.storage_key):
            raise TrollMusicError(f"The file for '{asset.title}' is missing from storage.")
        return self.storage.path(asset.storage_key)

    def store(
        self,
        path: Path | None,
        *,
        kind: str,
        title: str,
        info: ProviderInfo | None,
        mime_type: str | None = None,
        content: dict | None = None,
        meta: dict | None = None,
        duration: float | None = None,
        origin: str = "generated",
        parent: Asset | None = None,
        sources: dict[str, Asset | None] | None = None,
        params: dict | None = None,
    ) -> Asset:
        """Persist an output as an asset, with its file and provenance links."""
        asset = create_asset(
            self.session,
            kind=kind,
            title=title,
            project_id=self.job.project_id,
            content=content,
            params=params if params is not None else {k: v for k, v in self.params.items() if k != "project_id"},
            provider=info.name if info else None,
            model=info.model if info else None,
            is_mock=bool(info and info.is_mock),
            is_ai=bool(info and info.is_ai),
            origin=origin,
            parent=parent,
        )
        if path is not None:
            asset.storage_key = f"{kind}/{asset.id}{path.suffix.lower()}"
            asset.size_bytes = self.storage.save(path, asset.storage_key)
            asset.mime_type = mime_type
        asset.meta = meta
        asset.duration_seconds = duration
        for relation, source in (sources or {}).items():
            if source is not None:
                self.session.add(AssetLink(asset_id=asset.id, source_asset_id=source.id, relation=relation))
        self.session.flush()
        self.outputs.append(asset.id)
        return asset


# A handler does the work and returns the id of its primary output asset.
JobHandler = Callable[[JobContext], str]


class JobRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        handlers: dict[str, JobHandler],
        providers: ProviderManager,
        storage: Storage,
    ) -> None:
        self._session_factory = session_factory
        self._handlers = handlers
        self._providers = providers
        self._storage = storage

    def run(self, job_id: str) -> None:
        with self._session_factory() as session:
            job = session.get(Job, job_id)
            if job is None or job.status != JobStatus.QUEUED:
                return
            job.status = JobStatus.PROCESSING
            job.started_at = utcnow()
            job.stage = "Starting"
            session.commit()

            workdir = Path(tempfile.mkdtemp(prefix="troll-job-"))
            context = JobContext(session, job, self._providers, self._storage, workdir)
            try:
                asset_id = self._handlers[job.kind](context)
            except JobCancelled:
                session.rollback()
                self._discard(context)
                self._finish(session, job, JobStatus.CANCELLED, "Cancelled")
            except TrollMusicError as exc:
                session.rollback()
                self._discard(context)
                self._finish(session, job, JobStatus.FAILED, "Failed", exc.code, exc.message)
            except Exception:
                session.rollback()
                self._discard(context)
                log.exception("Job %s (%s) failed", job.id, job.kind)
                self._finish(session, job, JobStatus.FAILED, "Failed", "internal_error", "Something went wrong on our side.")
            else:
                job.result_asset_id = asset_id
                job.result_asset_ids = list(context.outputs)
                job.progress = 1.0
                self._finish(session, job, JobStatus.COMPLETED, "Done")
            finally:
                shutil.rmtree(workdir, ignore_errors=True)

    def _discard(self, context: JobContext) -> None:
        """Remove files written for assets whose rows were just rolled back.

        Outputs committed before the failure (a finished variation, a vocal
        track made on the way to a song) are real assets and are kept.
        """
        kept = []
        for asset_id in context.outputs:
            if context.session.get(Asset, asset_id) is not None:
                kept.append(asset_id)
                continue
            for path in context.storage.path("").glob(f"*/{asset_id}.*"):
                path.unlink(missing_ok=True)
        context.job.result_asset_ids = kept

    @staticmethod
    def _finish(session: Session, job: Job, status: str, stage: str, code: str | None = None, error: str | None = None) -> None:
        job.status = status
        job.stage = stage
        job.error_code = code
        job.error = error
        job.finished_at = utcnow()
        session.commit()


def queued_job_ids(session_factory: sessionmaker[Session]) -> list[str]:
    """Jobs a previous process accepted but never started, oldest first.

    They are safe to run after a restart: nothing was generated or charged yet.
    """
    with session_factory() as session:
        rows = session.execute(select(Job.id).where(Job.status == JobStatus.QUEUED).order_by(Job.created_at))
        return [row[0] for row in rows]


def fail_interrupted_jobs(session_factory: sessionmaker[Session]) -> int:
    """Mark jobs a previous process was in the middle of as failed.

    They are not re-run automatically: a half-finished job may already have
    called a paid provider, so retrying is left to the user (one click).
    """
    with session_factory() as session:
        result = session.execute(
            update(Job)
            .where(Job.status == JobStatus.PROCESSING)
            .values(
                status=JobStatus.FAILED,
                stage="Failed",
                error_code="interrupted",
                error="The server restarted before this job finished. Retry it.",
                finished_at=utcnow(),
            )
        )
        session.commit()
        return result.rowcount or 0
