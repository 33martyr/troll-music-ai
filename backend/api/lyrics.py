"""Lyrics and rap-battle endpoints.

Generation endpoints answer ``202 Accepted`` with a job; poll
``GET /api/jobs/{id}`` and read ``result_asset_id`` when it completes.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from backend.api.deps import ProvidersDep, QueueDep, SessionDep, load_asset, load_project, submit_job
from backend.core.errors import ApiError
from backend.models.schemas import (
    AssetOut,
    GenerateBattleBody,
    GenerateLyricsBody,
    ImportLyricsBody,
    JobOut,
    RegenerateSectionBody,
    RewriteLyricsBody,
    SaveLyricsBody,
    SuggestCharactersBody,
)
from backend.models.tables import AssetKind
from backend.services import lyrics as lyrics_service
from backend.services.assets import create_asset
from troll_music_ai import LyricsParseError
from troll_music_ai.lyrics import LyricsService, parse_plain_text

router = APIRouter(prefix="/api", tags=["lyrics"])


@router.post("/lyrics/generate", response_model=JobOut, status_code=202)
def generate_lyrics(body: GenerateLyricsBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    providers.require("text")  # fail now, with a clear message, rather than inside the job
    return submit_job(
        session, queue, kind=lyrics_service.JOB_GENERATE, project_id=body.project_id,
        params={"request": body.request.model_dump(mode="json")},
    )


@router.post("/lyrics/import", response_model=AssetOut, status_code=201)
def import_lyrics(body: ImportLyricsBody, session: SessionDep):
    """Store lyrics the user wrote themselves. No model is involved."""
    if body.project_id:
        load_project(session, body.project_id)
    try:
        lyrics = parse_plain_text(body.text, body.title.strip(), language=body.language)
    except LyricsParseError as exc:
        raise ApiError(422, "validation_error", "No lyric lines were found in that text.") from exc
    if not lyrics.sections:
        raise ApiError(422, "validation_error", "No lyric lines were found in that text.")
    asset = create_asset(
        session, kind=AssetKind.LYRICS, title=lyrics.title, project_id=body.project_id,
        content=lyrics.model_dump(mode="json"), is_ai=False, origin="imported",
    )
    session.commit()
    return asset


@router.post("/lyrics/{asset_id}/regenerate-section", response_model=JobOut, status_code=202)
def regenerate_section(asset_id: str, body: RegenerateSectionBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    providers.require("text")
    asset = load_asset(session, asset_id, AssetKind.LYRICS)
    sections = (asset.content or {}).get("sections", [])
    if not any(section.get("id") == body.section_id for section in sections):
        raise ApiError(404, "not_found", "That section does not exist in these lyrics.")
    return submit_job(
        session, queue, kind=lyrics_service.JOB_REGENERATE_SECTION, project_id=asset.project_id,
        params={"asset_id": asset.id, **body.model_dump(mode="json")},
    )


@router.post("/lyrics/{asset_id}/rewrite", response_model=JobOut, status_code=202)
def rewrite_lyrics(asset_id: str, body: RewriteLyricsBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    providers.require("text")
    asset = load_asset(session, asset_id, AssetKind.LYRICS)
    return submit_job(
        session, queue, kind=lyrics_service.JOB_REWRITE, project_id=asset.project_id,
        params={"asset_id": asset.id, **body.model_dump(mode="json")},
    )


@router.put("/lyrics/{asset_id}", response_model=AssetOut)
def save_lyrics(asset_id: str, body: SaveLyricsBody, session: SessionDep):
    """Save a manual edit as a new version. Works without any provider."""
    asset = load_asset(session, asset_id, AssetKind.LYRICS)
    try:
        edited = lyrics_service.save_manual_edit(session, asset, body)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    session.commit()
    return edited


@router.post("/battles/generate", response_model=JobOut, status_code=202)
def generate_battle(body: GenerateBattleBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    """A battle between two fictional characters, stored as lyrics with performers."""
    providers.require("text")
    return submit_job(
        session, queue, kind=lyrics_service.JOB_BATTLE, project_id=body.project_id,
        params={"request": body.request.model_dump(mode="json")},
    )


@router.post("/battles/characters")
def suggest_characters(body: SuggestCharactersBody, providers: ProvidersDep):
    """Fictional character ideas for a topic. A short, direct model call."""
    provider = providers.require("text")
    service = LyricsService(provider, json_mode=providers.json_mode())  # type: ignore[arg-type]
    characters = asyncio.run(service.suggest_characters(body.topic))
    return {"characters": characters, "provider": provider.info.name, "is_mock": provider.info.is_mock}
