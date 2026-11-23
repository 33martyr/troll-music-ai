"""Meme Factory: turn a finished troll into shareable formats.

Videos reuse the music-video renderer at another aspect ratio. Posters, award
cards, 'now playing' cards and reaction memes are drawn by Pillow over one
clean background picture made per run (from the active image provider, which
may be AI or the built-in card renderer). The existing cover is reused, not
remade.
"""

from __future__ import annotations

import asyncio
import random
import secrets

from backend.models.tables import Asset, AssetKind
from backend.services import visual_jobs
from backend.services.troll_jobs import _run
from backend.workers.runner import JobContext, JobHandler
from troll_music_ai import Lyrics, TrollMusicError
from troll_music_ai.providers import ImageGenerationProvider
from troll_music_ai.providers import meme_images
from troll_music_ai.providers.images import render_card
from troll_music_ai.types import ImageRequest

JOB_FACTORY = "factory.generate"

VIDEO_ITEMS = {"vertical_video": "9:16", "square_video": "1:1", "wide_video": "16:9"}
IMAGE_ITEMS = {
    "concert_poster": "Concert poster",
    "award_card": "Award card",
    "streaming_card": "Now playing card",
    "reaction_meme": "Reaction meme",
}
ITEMS = (*VIDEO_ITEMS, "square_cover", *IMAGE_ITEMS)


def _best_line(lyrics: Lyrics | None) -> str | None:
    if not lyrics:
        return None
    chorus = next((s for s in lyrics.sections if s.type.value == "chorus"), None)
    pool = (chorus or lyrics.sections[0]).lines
    return max(pool, key=len) if pool else None


def _background(context: JobContext, title: str, style: str) -> tuple[object, str]:
    """One text-free picture for every design in this run."""
    provider: ImageGenerationProvider | None = context.providers.get("image")  # type: ignore[assignment]
    request = ImageRequest(
        prompt=f"background art for a comedy {style} track called '{title}', bold, dramatic, colourful, no text, no logos",
        width=1024, height=1024, seed=secrets.randbelow(2**31), title=" ",
    )
    target = context.workdir / "factory_bg"
    if provider is not None:
        try:
            return asyncio.run(provider.generate_image(request, target)), provider.info.name
        except TrollMusicError as exc:
            context.progress(context.job.progress, f"Image model failed ({exc.code}); using a built-in background")
    return render_card(request, target), "typographic"


def generate_factory(context: JobContext) -> str:
    params = context.params
    track = context.asset(params["asset_id"], (AssetKind.SONG, AssetKind.BEAT))
    troll = (track.meta or {}).get("troll") or {}
    lyrics_asset = context.session.get(Asset, troll["lyrics_asset_id"]) if troll.get("lyrics_asset_id") else None
    lyrics = Lyrics.model_validate(lyrics_asset.content) if lyrics_asset and lyrics_asset.content else None
    title = (lyrics.title if lyrics else None) or track.title
    artist, target = troll.get("artist") or "TROLL-MUSIC-AI", troll.get("target") or "your friend"
    theme = params.get("theme") or "neon"
    items = [item for item in ITEMS if item in set(params.get("items") or [])]
    if not items:
        raise TrollMusicError("Choose at least one thing to make.")
    line = params.get("line") or _best_line(lyrics)

    step = 1 / len(items)
    made: list[str] = []
    background = None
    background_provider = None
    for index, item in enumerate(items):
        span = (index * step, (index + 1) * step)
        if item in VIDEO_ITEMS:
            video = _run(
                context, visual_jobs.generate_video,
                {"audio_asset_id": track.id, "lyrics_asset_id": lyrics_asset.id if lyrics_asset else None, "title": title,
                 "style": "meme", "aspect": VIDEO_ITEMS[item], "subtitles": True, "intro": {"presenter": artist, "title": title},
                 "notes": f"{theme} colour theme, meme music video, comedic"},
                span, f"Rendering the {VIDEO_ITEMS[item]} video",
            )
            video.meta = {**(video.meta or {}), "format": item, "theme": theme}
            made.append(video.id)
            continue
        if item == "square_cover":
            cover_id = troll.get("cover_asset_id")
            if cover_id and context.session.get(Asset, cover_id) is not None:
                context.outputs.append(cover_id)  # reused, not remade
                made.append(cover_id)
                continue
            cover = _run(
                context, visual_jobs.generate_artwork,
                {"title": title, "genre": troll.get("style") or "hip-hop", "style": "meme", "artist": artist,
                 "lyrics_asset_id": lyrics_asset.id if lyrics_asset else None},
                span, "Designing the cover",
            )
            made.append(cover.id)
            continue

        context.progress(span[0], f"Drawing the {IMAGE_ITEMS[item].lower()}")
        if background is None:
            background, background_provider = _background(context, title, troll.get("style") or "hip-hop")
        out = context.workdir / item
        award = None
        if item == "concert_poster":
            path = meme_images.concert_poster(out, artist=artist, title=title, target=target, theme=theme, background=background)
        elif item == "award_card":
            award = params.get("award") or random.choice(meme_images.AWARDS)
            reason = f"For the line “{line}”" if line else None
            path = meme_images.award_card(out, award=award, artist=artist, title=title, reason=reason, theme=theme, background=background)
        elif item == "streaming_card":
            cover_asset = context.session.get(Asset, troll["cover_asset_id"]) if troll.get("cover_asset_id") else None
            cover_path = context.file_of(cover_asset) if cover_asset and cover_asset.storage_key else None
            path = meme_images.streaming_card(out, artist=artist, title=title, line=line, theme=theme, cover=cover_path, background=background)
        else:
            path = meme_images.reaction_meme(
                out, top=f"{target} hearing this line:", bottom=line or title, theme=theme, background=background
            )
        asset = context.store(
            path,
            kind=AssetKind.ARTWORK,
            title=f"{title} · {award or IMAGE_ITEMS[item]}",
            info=None,
            mime_type="image/png",
            meta={
                "format": item,
                "theme": theme,
                "parody": True,
                # The design is drawn by Pillow; only the background picture may come from an AI model.
                "renderer": "pillow",
                "background_provider": background_provider,
                **({"award": award} if award else {}),
            },
            sources={"audio": track, "lyrics": lyrics_asset},
        )
        asset.provider, asset.is_ai = "meme-factory", False
        made.append(asset.id)
    context.progress(0.99, "Done")
    return made[0]


HANDLERS: dict[str, JobHandler] = {JOB_FACTORY: generate_factory}
