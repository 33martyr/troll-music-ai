"""Project management: CRUD, duplication and bundle export."""

from __future__ import annotations

import io
import json
import re
import zipfile

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.storage import Storage
from backend.models.schemas import AssetOut, ProjectOut
from backend.models.tables import Asset, AssetKind, AssetLink, Project, new_id
from troll_music_ai import Lyrics


def asset_counts(session: Session, project_ids: list[str]) -> dict[str, dict[str, int]]:
    """Latest-version asset counts per kind, keyed by project id."""
    counts: dict[str, dict[str, int]] = {pid: {} for pid in project_ids}
    if not project_ids:
        return counts
    rows = session.execute(
        select(Asset.project_id, Asset.kind, func.count())
        .where(Asset.project_id.in_(project_ids), Asset.is_latest.is_(True))
        .group_by(Asset.project_id, Asset.kind)
    )
    for project_id, kind, count in rows:
        counts[project_id][kind] = count
    return counts


def to_out(session: Session, project: Project) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    out.asset_counts = asset_counts(session, [project.id])[project.id]
    return out


def list_projects(session: Session) -> list[ProjectOut]:
    projects = list(session.scalars(select(Project).order_by(Project.updated_at.desc())))
    counts = asset_counts(session, [p.id for p in projects])
    outs = []
    for project in projects:
        out = ProjectOut.model_validate(project)
        out.asset_counts = counts[project.id]
        outs.append(out)
    return outs


def duplicate_project(session: Session, storage: Storage, source: Project) -> Project:
    """Deep copy: every asset version, file and provenance link gets a new id."""
    copy = Project(name=f"{source.name} (copy)"[:120], description=source.description)
    session.add(copy)
    session.flush()

    assets = list(session.scalars(select(Asset).where(Asset.project_id == source.id)))
    id_map = {asset.id: new_id() for asset in assets}
    for asset in assets:
        storage_key = None
        if asset.storage_key and storage.exists(asset.storage_key):
            # Each copy owns its file, so deleting one project never breaks the other.
            storage_key = asset.storage_key.replace(asset.id, id_map[asset.id])
            storage.copy(asset.storage_key, storage_key)
        session.add(
            Asset(
                id=id_map[asset.id],
                project_id=copy.id,
                kind=asset.kind,
                title=asset.title,
                content=asset.content,
                storage_key=storage_key,
                mime_type=asset.mime_type,
                size_bytes=asset.size_bytes,
                duration_seconds=asset.duration_seconds,
                meta=asset.meta,
                is_ai=asset.is_ai,
                params=asset.params,
                provider=asset.provider,
                model=asset.model,
                is_mock=asset.is_mock,
                origin=asset.origin,
                parent_id=id_map.get(asset.parent_id) if asset.parent_id else None,
                root_id=id_map.get(asset.root_id, id_map[asset.id]),
                version=asset.version,
                is_latest=asset.is_latest,
                approved=asset.approved,
                created_at=asset.created_at,
            )
        )
    if id_map:
        links = session.scalars(select(AssetLink).where(AssetLink.asset_id.in_(id_map)))
        for link in links:
            if link.source_asset_id in id_map:
                session.add(
                    AssetLink(
                        asset_id=id_map[link.asset_id],
                        source_asset_id=id_map[link.source_asset_id],
                        relation=link.relation,
                    )
                )
    session.flush()
    return copy


def slugify(text: str, fallback: str = "untitled") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or fallback


def delete_project(session: Session, storage: Storage, project: Project) -> None:
    """Delete the project, everything in it and the files behind it."""
    keys = list(
        session.scalars(
            select(Asset.storage_key).where(Asset.project_id == project.id, Asset.storage_key.is_not(None))
        )
    )
    session.delete(project)
    session.flush()
    for key in keys:
        storage.delete(key)


def export_bundle(session: Session, storage: Storage, project: Project) -> bytes:
    """Zip with a manifest of every asset version, rendered lyrics and the
    media files of the latest versions."""
    assets = list(
        session.scalars(
            select(Asset)
            .where(Asset.project_id == project.id)
            .order_by(Asset.created_at, Asset.version)
        )
    )
    manifest = {
        "format": "troll-music-ai/project-bundle@1",
        "project": to_out(session, project).model_dump(mode="json"),
        "assets": [AssetOut.model_validate(a).model_dump(mode="json", exclude={"file_token"}) for a in assets],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("project.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        for asset in assets:
            if asset.is_latest and asset.storage_key and storage.exists(asset.storage_key):
                suffix = asset.storage_key.rsplit(".", 1)[-1]
                bundle.write(
                    storage.path(asset.storage_key),
                    f"{asset.kind}/{slugify(asset.title)}-{asset.id[:6]}.{suffix}",
                    compress_type=zipfile.ZIP_STORED,  # media is already compressed
                )
            if asset.kind != AssetKind.LYRICS or not asset.is_latest or not asset.content:
                continue
            lyrics = Lyrics.model_validate(asset.content)
            name = f"lyrics/{slugify(asset.title)}-{asset.root_id[:6]}"
            bundle.writestr(f"{name}.md", lyrics.to_markdown())
            bundle.writestr(f"{name}.txt", lyrics.to_text())
    return buffer.getvalue()
