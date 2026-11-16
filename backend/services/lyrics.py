"""Lyrics and rap-battle job handlers, imports and manual edits.

Each handler loads what it needs, calls the toolkit's ``LyricsService`` and
stores the result as a new asset version. Nothing here regenerates an asset
the user did not ask about.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from backend.models.schemas import SaveLyricsBody
from backend.models.tables import Asset, AssetKind
from backend.services.assets import create_asset
from backend.workers.runner import JobContext, JobHandler
from troll_music_ai import Lyrics, LyricSection, LyricsRequest, RewriteMode, TrollMusicError
from troll_music_ai.lyrics import LyricsService
from troll_music_ai.types import BattleRequest

JOB_GENERATE = "lyrics.generate"
JOB_REGENERATE_SECTION = "lyrics.regenerate_section"
JOB_REWRITE = "lyrics.rewrite"
JOB_BATTLE = "battle.generate"


def _service(context: JobContext) -> LyricsService:
    provider = context.providers.require("text")
    context.using(provider)
    return LyricsService(provider, json_mode=context.providers.json_mode())  # type: ignore[arg-type]


def _load(context: JobContext) -> tuple[Asset, Lyrics, LyricsRequest | None]:
    asset = context.asset(context.params["asset_id"], AssetKind.LYRICS)
    if not asset.content:
        raise TrollMusicError("The lyrics this job refers to are empty.")
    # Battle lyrics keep a BattleRequest in params, which is not a LyricsRequest.
    request = LyricsRequest.model_validate(asset.params) if asset.params and "prompt" in asset.params else None
    return asset, Lyrics.model_validate(asset.content), request


def _store(context: JobContext, lyrics: Lyrics, *, origin: str, params: dict | None, parent: Asset | None = None) -> str:
    context.progress(0.95, "Saving")
    meta = lyrics.meta
    asset = create_asset(
        context.session,
        kind=AssetKind.LYRICS,
        title=lyrics.title,
        project_id=context.job.project_id,
        content=lyrics.model_dump(mode="json"),
        params=params,
        provider=meta.provider if meta else None,
        model=meta.model if meta else None,
        is_mock=bool(meta and meta.is_mock),
        is_ai=not (meta and meta.is_mock),
        origin=origin,
        parent=parent,
    )
    context.outputs.append(asset.id)
    return asset.id


def generate(context: JobContext) -> str:
    request = LyricsRequest.model_validate(context.params["request"])
    lyrics = asyncio.run(_service(context).generate(request, on_progress=context.progress))
    return _store(context, lyrics, origin="generated", params=request.model_dump(mode="json"))


def generate_battle(context: JobContext) -> str:
    request = BattleRequest.model_validate(context.params["request"])
    lyrics = asyncio.run(_service(context).generate_battle(request, on_progress=context.progress))
    return _store(context, lyrics, origin="battle", params=request.model_dump(mode="json"))


def regenerate_section(context: JobContext) -> str:
    asset, lyrics, request = _load(context)
    updated = asyncio.run(
        _service(context).regenerate_section(
            lyrics,
            context.params["section_id"],
            request=request,
            instruction=context.params.get("instruction"),
            on_progress=context.progress,
        )
    )
    return _store(context, updated, origin="section_regenerated", params=asset.params, parent=asset)


def rewrite(context: JobContext) -> str:
    asset, lyrics, request = _load(context)
    updated = asyncio.run(
        _service(context).rewrite(
            lyrics,
            RewriteMode(context.params["mode"]),
            request=request,
            instruction=context.params.get("instruction"),
            rhyme_scheme=context.params.get("rhyme_scheme"),
            on_progress=context.progress,
        )
    )
    return _store(context, updated, origin="rewritten", params=asset.params, parent=asset)


HANDLERS: dict[str, JobHandler] = {
    JOB_GENERATE: generate,
    JOB_REGENERATE_SECTION: regenerate_section,
    JOB_REWRITE: rewrite,
    JOB_BATTLE: generate_battle,
}


def save_manual_edit(session: Session, asset: Asset, body: SaveLyricsBody) -> Asset:
    """Store the user's edit as a new version. No model is involved."""
    current = Lyrics.model_validate(asset.content)
    performers = {section.id: section.performer for section in current.sections}
    sections = []
    for edit in body.sections:
        lines = [line.strip() for line in edit.lines if line.strip()]
        if not lines:
            continue
        fields = {"type": edit.type, "label": edit.label.strip(), "lines": lines}
        if edit.id:
            fields |= {"id": edit.id, "performer": performers.get(edit.id)}
        sections.append(LyricSection(**fields))
    if not sections:
        raise ValueError("Lyrics need at least one section with a line in it.")

    edited = current.model_copy(update={"title": body.title.strip(), "sections": sections})
    return create_asset(
        session,
        kind=AssetKind.LYRICS,
        title=edited.title,
        project_id=asset.project_id,
        content=edited.model_dump(mode="json"),
        params=asset.params,
        provider=asset.provider,
        model=asset.model,
        is_mock=asset.is_mock,
        is_ai=asset.is_ai,
        origin="edited",
        parent=asset,
    )
