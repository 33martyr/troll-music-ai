"""Asset persistence with version lineage."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.core.storage import Storage
from backend.models.tables import Asset, AssetLink, Project, new_id, utcnow


def create_asset(
    session: Session,
    *,
    kind: str,
    title: str,
    project_id: str | None,
    content: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    is_mock: bool = False,
    is_ai: bool = True,
    origin: str = "generated",
    parent: Asset | None = None,
) -> Asset:
    """Insert an asset. With ``parent`` it becomes the newest version of that
    lineage; the parent itself is never modified apart from ``is_latest``."""
    asset_id = new_id()
    version = 1
    root_id = asset_id
    if parent is not None:
        root_id = parent.root_id
        project_id = parent.project_id
        latest = session.scalar(select(func.max(Asset.version)).where(Asset.root_id == root_id))
        version = (latest or parent.version) + 1
        session.execute(update(Asset).where(Asset.root_id == root_id).values(is_latest=False))

    asset = Asset(
        id=asset_id,
        project_id=project_id,
        kind=kind,
        title=title[:200],
        content=content,
        params=params,
        provider=provider,
        model=model,
        is_mock=is_mock,
        is_ai=is_ai,
        origin=origin,
        parent_id=parent.id if parent else None,
        root_id=root_id,
        version=version,
        is_latest=True,
    )
    session.add(asset)
    if project_id:
        session.execute(
            update(Project).where(Project.id == project_id).values(updated_at=utcnow())
        )
    session.flush()
    return asset


def list_assets(
    session: Session,
    *,
    project_id: str | None = None,
    unsorted_only: bool = False,
    kind: str | None = None,
    latest_only: bool = True,
    limit: int = 100,
) -> list[Asset]:
    query = select(Asset).order_by(Asset.created_at.desc(), Asset.version.desc()).limit(limit)
    if project_id:
        query = query.where(Asset.project_id == project_id)
    elif unsorted_only:
        query = query.where(Asset.project_id.is_(None))
    if kind:
        query = query.where(Asset.kind.in_(kind.split(",")))
    if latest_only:
        query = query.where(Asset.is_latest.is_(True))
    return list(session.scalars(query))


def lineage(session: Session, root_id: str) -> list[Asset]:
    """Every version of an asset, newest first."""
    return list(
        session.scalars(
            select(Asset).where(Asset.root_id == root_id).order_by(Asset.version.desc())
        )
    )


def sources_of(session: Session, asset_id: str) -> list[tuple[str, Asset]]:
    """The assets this one was made from, as ``(relation, asset)``."""
    rows = session.execute(
        select(AssetLink.relation, Asset)
        .join(Asset, Asset.id == AssetLink.source_asset_id)
        .where(AssetLink.asset_id == asset_id)
    )
    return [(relation, asset) for relation, asset in rows]


def delete_assets(session: Session, storage: Storage, assets: list[Asset]) -> int:
    """Delete rows, provenance links and stored files."""
    ids = [asset.id for asset in assets]
    if not ids:
        return 0
    keys = [asset.storage_key for asset in assets if asset.storage_key]
    session.execute(
        delete(AssetLink).where(AssetLink.asset_id.in_(ids) | AssetLink.source_asset_id.in_(ids))
    )
    session.execute(delete(Asset).where(Asset.id.in_(ids)))
    session.flush()
    for key in keys:
        storage.delete(key)
    return len(ids)


def delete_lineage(session: Session, storage: Storage, root_id: str) -> int:
    return delete_assets(session, storage, lineage(session, root_id))


def move_lineage(session: Session, root_id: str, project_id: str | None) -> None:
    session.execute(update(Asset).where(Asset.root_id == root_id).values(project_id=project_id))
