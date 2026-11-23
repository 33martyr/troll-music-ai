"""Troll Universe and Roast Awards jobs, and the card renderers they share.

Portraits come from the active image provider (AI or the built-in card
renderer). Collectible cards, rivalry posters and award cards are drawn by
Pillow on top. Awards are chosen by the text model from a fixed list.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.storage import Storage
from backend.models.tables import Asset, AssetKind, Rapper, Rivalry, RivalryResult
from backend.services.assets import create_asset, sources_of
from backend.workers.runner import JobContext, JobHandler
from troll_music_ai import Lyrics, TrollMusicError
from troll_music_ai.lyrics import LyricsService
from troll_music_ai.providers import ImageGenerationProvider, meme_images
from troll_music_ai.providers.images import render_card
from troll_music_ai.troll import STYLES
from troll_music_ai.types import ImageRequest
from troll_music_ai.universe import RapperStats

JOB_AVATAR = "universe.avatar"
JOB_AWARDS = "awards.generate"


def record_of(rapper: Rapper) -> str:
    return f"{rapper.wins}W {rapper.losses}L {rapper.draws}D"


def _file(storage: Storage, session: Session, asset_id: str | None) -> Path | None:
    asset = session.get(Asset, asset_id) if asset_id else None
    if asset and asset.storage_key and storage.exists(asset.storage_key):
        return storage.path(asset.storage_key)
    return None


def _store_png(session: Session, storage: Storage, path: Path, *, title: str, project_id: str | None, meta: dict) -> Asset:
    asset = create_asset(session, kind=AssetKind.ARTWORK, title=title, project_id=project_id, provider="troll-universe", is_ai=False, origin="generated")
    asset.storage_key = f"artwork/{asset.id}.png"
    asset.size_bytes = storage.save(path, asset.storage_key)
    asset.mime_type = "image/png"
    asset.meta = meta
    session.flush()
    return asset


def render_rapper_card(session: Session, storage: Storage, rapper: Rapper, workdir: Path, theme: str = "neon") -> Asset:
    """Draw (or redraw) the rapper's collectible card and point the rapper at it."""
    stats = RapperStats(**(rapper.stats or {}))
    path = meme_images.rapper_card(
        workdir / f"card_{rapper.id}", name=rapper.name, catchphrase=rapper.catchphrase, style=STYLES.get(rapper.style, ("Trap",))[0],
        stats=stats.model_dump(), overall=stats.overall, record=record_of(rapper), titles=list(rapper.titles or []),
        avatar=_file(storage, session, rapper.avatar_asset_id), theme=theme,
    )
    card = _store_png(session, storage, path, title=f"{rapper.name} · rapper card", project_id=None,
                      meta={"format": "rapper_card", "rapper_id": rapper.id, "parody": True, "renderer": "pillow"})
    rapper.card_asset_id = card.id
    return card


def render_rivalry_poster(session: Session, storage: Storage, rivalry: Rivalry, workdir: Path, theme: str = "grunge") -> Asset:
    a, b = session.get(Rapper, rivalry.rapper_a_id), session.get(Rapper, rivalry.rapper_b_id)
    wins_a, wins_b, _ = rivalry_record(session, rivalry)
    champion = champion_of(session, rivalry)
    path = meme_images.rivalry_poster(
        workdir / f"rivalry_{rivalry.id}", a=a.name, b=b.name, record=f"{wins_a} - {wins_b}",
        tagline=rivalry.tagline or f"{a.catchphrase or ''} / {b.catchphrase or ''}".strip(" /") or "Only one leaves with the belt.",
        avatar_a=_file(storage, session, a.avatar_asset_id), avatar_b=_file(storage, session, b.avatar_asset_id),
        champion=champion.name if champion else None, theme=theme,
    )
    return _store_png(session, storage, path, title=f"{a.name} vs {b.name} · rivalry poster", project_id=rivalry.project_id,
                      meta={"format": "rivalry_poster", "rivalry_id": rivalry.id, "parody": True, "renderer": "pillow"})


# ------------------------------- rivalries --------------------------------- #

CHAMPION_WINS = 3


def rivalry_record(session: Session, rivalry: Rivalry) -> tuple[int, int, int]:
    results = list(session.scalars(select(RivalryResult).where(RivalryResult.rivalry_id == rivalry.id)))
    wins_a = sum(r.winner_id == rivalry.rapper_a_id for r in results)
    wins_b = sum(r.winner_id == rivalry.rapper_b_id for r in results)
    return wins_a, wins_b, sum(r.winner_id is None for r in results)


def champion_of(session: Session, rivalry: Rivalry) -> Rapper | None:
    """Champion: first to 3 wins, and ahead on wins."""
    wins_a, wins_b, _ = rivalry_record(session, rivalry)
    if max(wins_a, wins_b) >= CHAMPION_WINS and wins_a != wins_b:
        return session.get(Rapper, rivalry.rapper_a_id if wins_a > wins_b else rivalry.rapper_b_id)
    return None


def recount(session: Session, rapper: Rapper) -> None:
    """Rebuild a rapper's record and titles from every settled battle."""
    rivalries = list(session.scalars(select(Rivalry).where((Rivalry.rapper_a_id == rapper.id) | (Rivalry.rapper_b_id == rapper.id))))
    wins = losses = draws = 0
    titles: list[str] = []
    for rivalry in rivalries:
        for result in session.scalars(select(RivalryResult).where(RivalryResult.rivalry_id == rivalry.id)):
            if result.winner_id is None:
                draws += 1
            elif result.winner_id == rapper.id:
                wins += 1
            else:
                losses += 1
        champion = champion_of(session, rivalry)
        if champion and champion.id == rapper.id:
            other = session.get(Rapper, rivalry.rapper_b_id if rivalry.rapper_a_id == rapper.id else rivalry.rapper_a_id)
            titles.append(f"Champion over {other.name}" if other else "Rivalry Champion")
    rapper.wins, rapper.losses, rapper.draws, rapper.titles = wins, losses, draws, titles


# --------------------------------- jobs ------------------------------------ #


def generate_avatar(context: JobContext) -> str:
    """A portrait for a fictional rapper, then a fresh collectible card."""
    rapper = context.session.get(Rapper, context.params["rapper_id"])
    if rapper is None:
        raise TrollMusicError("That rapper no longer exists.")
    provider: ImageGenerationProvider | None = context.providers.get("image")  # type: ignore[assignment]
    prompt = (
        f"portrait of a fictional cartoon rapper called {rapper.name}, {rapper.personality}, "
        f"{STYLES.get(rapper.style, ('',))[0]} music style, funny, exaggerated, bold colours, album-art lighting, no text, no logos"
    )
    request = ImageRequest(prompt=prompt[:1900], width=1024, height=1024, seed=secrets.randbelow(2**31), title=" ")
    context.progress(0.1, f"Painting {rapper.name}")
    used = provider
    if provider is not None:
        info = context.using(provider)
        try:
            raw = asyncio.run(provider.generate_image(request, context.workdir / "avatar"))
        except TrollMusicError as exc:
            context.progress(0.5, f"Image model failed ({exc.code}); using a built-in portrait card")
            raw, used, info = render_card(request, context.workdir / "avatar"), None, None
    else:
        raw, info = render_card(request, context.workdir / "avatar"), None
    avatar = context.store(
        Path(raw), kind=AssetKind.ARTWORK, title=f"{rapper.name} · portrait", info=info if used else None, mime_type="image/png",
        meta={"format": "rapper_avatar", "rapper_id": rapper.id, "prompt": prompt},
    )
    if not used:
        avatar.provider, avatar.model, avatar.is_ai = "typographic", "troll-cards-1", False
    rapper.avatar_asset_id = avatar.id
    context.progress(0.85, "Printing the collectible card")
    card = render_rapper_card(context.session, context.storage, rapper, context.workdir)
    context.outputs.append(card.id)
    return card.id


def generate_awards(context: JobContext) -> str:
    """Roast Awards for one track: the text model picks awards from the fixed
    list (an opinion), and each becomes an award card."""
    track = context.asset(context.params["asset_id"], (AssetKind.SONG, AssetKind.BEAT, AssetKind.VIDEO))
    troll = (track.meta or {}).get("troll") or {}
    if track.kind == AssetKind.VIDEO and not troll:
        track = next((s for r, s in sources_of(context.session, track.id) if r == "audio"), track)
        troll = (track.meta or {}).get("troll") or {}
    lyrics_asset = context.session.get(Asset, troll["lyrics_asset_id"]) if troll.get("lyrics_asset_id") else None
    if lyrics_asset is None:
        lyrics_asset = next((s for r, s in sources_of(context.session, track.id) if r == "lyrics"), None)
    if lyrics_asset is None or not lyrics_asset.content:
        raise TrollMusicError("Awards need a track with lyrics.")
    lyrics = Lyrics.model_validate(lyrics_asset.content)
    provider = context.providers.require("text")
    info = context.using(provider)
    context.progress(0.1, "The Trollies jury is deliberating")
    service = LyricsService(provider, json_mode=context.providers.json_mode())  # type: ignore[arg-type]
    awards, model = asyncio.run(service.roast_awards(lyrics, int(context.params.get("count") or 3)))
    artist = troll.get("artist") or "TROLL-MUSIC-AI"
    theme = context.params.get("theme") or "gold"
    cover = context.session.get(Asset, troll["cover_asset_id"]) if troll.get("cover_asset_id") else None
    background = context.file_of(cover) if cover and cover.storage_key else None
    first = ""
    for index, award in enumerate(awards):
        context.progress(0.5 + 0.45 * index / len(awards), f"Engraving {award.award}")
        path = meme_images.award_card(
            context.workdir / f"award_{index}", award=award.award, artist=artist, title=lyrics.title,
            reason=award.reason, theme=theme, background=background,
        )
        asset = context.store(
            path, kind=AssetKind.ARTWORK, title=f"{lyrics.title} · {award.award}", info=None, mime_type="image/png",
            meta={
                "format": "award_card", "award": award.award, "reason": award.reason, "line": award.line,
                "awards_for": track.id, "parody": True, "renderer": "pillow",
                # Who picked the award: an AI opinion, or a mock.
                "judged_by": model or info.model, "judged_by_provider": info.name, "judged_mock": info.is_mock,
            },
            sources={"audio": track, "lyrics": lyrics_asset},
        )
        asset.provider, asset.is_ai, asset.is_mock = "troll-awards", not info.is_mock, info.is_mock
        first = first or asset.id
    return first


HANDLERS: dict[str, JobHandler] = {JOB_AVATAR: generate_avatar, JOB_AWARDS: generate_awards}
