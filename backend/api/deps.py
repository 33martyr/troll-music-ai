"""Shared request dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.core.errors import not_found
from backend.core.storage import Storage
from backend.models.tables import Asset, AssetKind, Job, Project
from backend.services.providers import ProviderManager
from backend.workers.queue import JobQueue


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue


def get_providers(request: Request) -> ProviderManager:
    return request.app.state.providers


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


SessionDep = Annotated[Session, Depends(get_session)]
QueueDep = Annotated[JobQueue, Depends(get_queue)]
ProvidersDep = Annotated[ProviderManager, Depends(get_providers)]
StorageDep = Annotated[Storage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

_NAMES = {AssetKind.LYRICS: "Lyrics", AssetKind.BEAT: "Beat", AssetKind.VOCALS: "Vocals", AssetKind.SONG: "Song"}


def load_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise not_found("Project")
    return project


def load_asset(session: Session, asset_id: str, kind: str | tuple[str, ...] | None = None) -> Asset:
    asset = session.get(Asset, asset_id)
    kinds = (kind,) if isinstance(kind, str) else kind
    if asset is None or (kinds and asset.kind not in kinds):
        raise not_found(_NAMES.get(kinds[0], "Asset") if kinds else "Asset")
    return asset


def submit_job(session: Session, queue: JobQueue, *, kind: str, project_id: str | None, params: dict, retry_of: str | None = None) -> Job:
    """Create the job row, enqueue it and return its current state."""
    if project_id:
        load_project(session, project_id)
    job = Job(kind=kind, project_id=project_id, params=params, retry_of=retry_of)
    session.add(job)
    session.commit()
    queue.enqueue(job.id)
    session.refresh(job)
    return job
