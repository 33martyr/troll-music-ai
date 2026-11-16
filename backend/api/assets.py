from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Response, UploadFile
from fastapi.responses import FileResponse

from backend.api.deps import SessionDep, SettingsDep, StorageDep, load_asset, load_project
from backend.audio import ffmpeg
from backend.core.errors import ApiError, not_found
from backend.models.schemas import AssetOut, AssetUpdate
from backend.models.tables import AssetKind
from backend.services import assets as asset_service
from backend.services.projects import slugify
from backend.services.voices import save_upload
from troll_music_ai import Lyrics

router = APIRouter(prefix="/api/assets", tags=["assets"])

UPLOAD_KINDS = (AssetKind.BEAT, AssetKind.VOCALS, AssetKind.SONG)
_EXTENSIONS = {"audio/mpeg": "mp3", "video/mp4": "mp4", "image/png": "png", "image/jpeg": "jpg", "audio/wav": "wav"}


@router.get("", response_model=list[AssetOut])
def list_assets(
    session: SessionDep,
    kind: str | None = None,
    project_id: str | None = None,
    unsorted: bool = False,
    limit: int = 50,
):
    """Latest version of each asset, newest first. ``kind`` accepts a
    comma-separated list. ``unsorted=true`` returns only assets outside projects."""
    return asset_service.list_assets(
        session, project_id=project_id, unsorted_only=unsorted, kind=kind, limit=max(1, min(limit, 200))
    )


@router.post("/upload", response_model=AssetOut, status_code=201)
def upload_asset(
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = AssetKind.BEAT,
    title: Annotated[str, Form()] = "",
    project_id: Annotated[str | None, Form()] = None,
    bpm: Annotated[float | None, Form()] = None,
):
    """Upload your own beat, vocal or song. The file is checked with FFmpeg and
    re-encoded to MP3, so a renamed non-audio file is rejected."""
    if kind not in UPLOAD_KINDS:
        raise ApiError(422, "validation_error", f"kind must be one of: {', '.join(UPLOAD_KINDS)}.")
    if bpm is not None and not 50 <= bpm <= 220:
        raise ApiError(422, "validation_error", "bpm must be between 50 and 220.")
    if project_id:
        load_project(session, project_id)
    workdir = Path(tempfile.mkdtemp(prefix="troll-upload-"))
    try:
        raw = workdir / "upload"
        save_upload(file.file, raw, settings.max_upload_mb * 1024 * 1024)
        info = ffmpeg.probe(raw)
        if not info.has_audio or info.duration < 1:
            raise ApiError(422, "invalid_media", "That file has no usable audio in it.")
        if info.duration > 900:
            raise ApiError(422, "invalid_media", "Audio uploads are limited to 15 minutes.")
        final = ffmpeg.finalize_audio(raw, workdir / "audio.mp3", normalize=False, fade_out=0)
        name = title.strip() or Path(file.filename or "Upload").stem
        asset = asset_service.create_asset(
            session, kind=kind, title=name, project_id=project_id or None, is_ai=False, origin="uploaded",
        )
        asset.storage_key = f"{kind}/{asset.id}.mp3"
        asset.size_bytes = storage.save(final, asset.storage_key)
        asset.mime_type = "audio/mpeg"
        asset.duration_seconds = ffmpeg.probe(final).duration
        asset.meta = {"bpm": bpm, "bpm_exact": bpm is not None, "original_filename": (file.filename or "")[:200]}
        session.commit()
        return asset
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: str, session: SessionDep):
    return load_asset(session, asset_id)


@router.get("/{asset_id}/history", response_model=list[AssetOut])
def asset_history(asset_id: str, session: SessionDep):
    return asset_service.lineage(session, load_asset(session, asset_id).root_id)


@router.get("/{asset_id}/sources")
def asset_sources(asset_id: str, session: SessionDep):
    """The assets this one was made from."""
    load_asset(session, asset_id)
    return [
        {"relation": relation, "asset": AssetOut.model_validate(source)}
        for relation, source in asset_service.sources_of(session, asset_id)
    ]


@router.patch("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: str, body: AssetUpdate, session: SessionDep):
    asset = load_asset(session, asset_id)
    if body.approved is not None:
        asset.approved = body.approved
    if body.title is not None:
        asset.title = body.title.strip()
    if "project_id" in body.model_fields_set:
        if body.project_id:
            load_project(session, body.project_id)
        asset_service.move_lineage(session, asset.root_id, body.project_id or None)
    session.commit()
    session.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: str, session: SessionDep, storage: StorageDep):
    """Deletes the asset, all of its versions and their files."""
    asset_service.delete_lineage(session, storage, load_asset(session, asset_id).root_id)
    session.commit()
    return Response(status_code=204)


# The path parameter is named file_id so a signed ?token= can authorize it
# (see backend.core.security): media elements cannot send an Authorization header.
@router.get("/{file_id}/file")
def asset_file(file_id: str, session: SessionDep, storage: StorageDep, download: bool = False):
    """The asset's media file. Supports range requests, so players can seek."""
    asset = load_asset(session, file_id)
    if not asset.storage_key or not storage.exists(asset.storage_key):
        raise not_found("File")
    extension = _EXTENSIONS.get(asset.mime_type or "", Path(asset.storage_key).suffix.lstrip("."))
    return FileResponse(
        storage.path(asset.storage_key),
        media_type=asset.mime_type or "application/octet-stream",
        filename=f"{slugify(asset.title, asset.kind)}.{extension}",
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{asset_id}/export")
def export_asset(asset_id: str, session: SessionDep, format: Literal["txt", "md"] = "txt"):
    asset = load_asset(session, asset_id)
    if asset.kind != AssetKind.LYRICS or not asset.content:
        raise ApiError(400, "not_exportable", "Only lyrics export as text. Use /file for media.")
    lyrics = Lyrics.model_validate(asset.content)
    body, media_type = (
        (lyrics.to_markdown(), "text/markdown") if format == "md" else (lyrics.to_text(), "text/plain")
    )
    filename = f"{slugify(asset.title, 'lyrics')}.{format}"
    return Response(
        body,
        media_type=f"{media_type}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
