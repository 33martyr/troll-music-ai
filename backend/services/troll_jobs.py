"""One-button meme generation.

A troll job runs the existing stage handlers (lyrics or battle, vocals, beat,
mix, cover, video) one after another inside a single job, each with its own
parameters and its own slice of the progress bar. Every stage still stores its
own asset with its own provenance, so a result can be reopened and any part
redone in the studio pages, and every honesty label (AI, built-in, mock,
spoken-not-sung) is the one that stage would show on its own.
"""

from __future__ import annotations

import asyncio
import math
import secrets
from typing import Any

from backend.models.tables import Asset
from backend.services import audio_jobs, lyrics as lyrics_jobs, visual_jobs
from backend.workers.runner import JobContext, JobHandler
from troll_music_ai import TrollMusicError
from troll_music_ai.lyrics import battle_request_for, lyrics_request_for
from troll_music_ai.providers.procedural import preset_for
from troll_music_ai.troll import KIND_LABELS, TrollKind, TrollRequest, beat_title, rapper_name
from troll_music_ai.types import BeatRequest

JOB_TROLL = "troll.generate"

# Stage labels, in the order they run. The web app's timeline reads them from
# the job's ``stage`` ("<label> · <detail>"), so keep them stable.
STEP_WORDS = "Writing the lyrics"
STEP_VOCALS = "Recording the vocals"
STEP_BEAT = "Building the beat"
STEP_MIX = "Mixing the track"
STEP_COVER = "Designing the cover"
STEP_VIDEO = "Rendering the video"

_ENERGY = {"friendly": 3, "savage": 4, "brutal": 5, "nuclear": 5}


class _Step:
    """Runs another handler inside this job, with its own params and a slice of
    the progress bar. Everything else (session, storage, outputs) is shared."""

    def __init__(self, parent: JobContext, params: dict[str, Any], span: tuple[float, float], label: str) -> None:
        self._parent, self._params, self._span, self._label = parent, params, span, label

    def __getattr__(self, name: str) -> Any:
        return getattr(self._parent, name)

    @property
    def params(self) -> dict[str, Any]:
        return self._params

    def progress(self, fraction: float, stage: str) -> None:
        lo, hi = self._span
        self._parent.progress(lo + (hi - lo) * max(0.0, min(1.0, fraction)), f"{self._label} · {stage}")

    def store(self, path, **kwargs) -> Asset:
        kwargs.setdefault("params", self._params)
        return self._parent.store(path, **kwargs)


def _run(context: JobContext, handler: JobHandler, params: dict, span: tuple[float, float], label: str) -> Asset:
    step = _Step(context, params, span, label)
    step.progress(0.0, "starting")
    asset_id = handler(step)  # type: ignore[arg-type]
    asset = context.session.get(Asset, asset_id)
    if asset is None:
        raise TrollMusicError(f"{label} produced nothing.")
    return asset


def _second_voice(context: JobContext) -> str | None:
    """A different stock voice for the other rapper in a battle, if there is one."""
    provider = context.providers.get("voice")
    if provider is None:
        return None
    try:
        voices = asyncio.run(provider.voices())  # type: ignore[attr-defined]
    except TrollMusicError:
        return None
    return voices[1] if len(voices) > 1 else None


def generate_troll(context: JobContext) -> str:
    request = TrollRequest.model_validate(context.params["request"])
    with_video = request.kind is TrollKind.MEME_VIDEO or bool(context.params.get("with_video"))
    with_cover = bool(context.params.get("with_cover", True)) or request.kind is TrollKind.FUNNY_BEAT
    artist = request.rapper_name or rapper_name(request.target)
    # A battle is billed as a match-up on the cover and the video's opening card.
    billing = f"{artist} vs {request.who}" if request.kind is TrollKind.RAP_BATTLE else artist
    preset_bpm = preset_for(request.beat_genre)["bpm"]
    warnings: list[str] = []

    # ---- 1. words (everything but a funny beat). A remix reuses its lyrics. ----
    lyrics_asset: Asset | None = None
    reused = bool(context.params.get("lyrics_asset_id"))
    if reused:
        lyrics_asset = context.asset(context.params["lyrics_asset_id"], "lyrics")
        if context.params.get("rewrite_instruction"):
            lyrics_asset = _run(
                context, lyrics_jobs.rewrite,
                {"asset_id": lyrics_asset.id, "mode": "custom", "instruction": context.params["rewrite_instruction"]},
                (0.0, 0.3), STEP_WORDS,
            )
        # Redo only some sections (one person's verse, the chorus); the rest is kept word for word.
        sections = list(context.params.get("regenerate_sections") or [])
        for index, section_id in enumerate(sections):
            span = (0.3 * index / len(sections), 0.3 * (index + 1) / len(sections))
            lyrics_asset = _run(
                context, lyrics_jobs.regenerate_section,
                {"asset_id": lyrics_asset.id, "section_id": section_id, "instruction": context.params.get("section_instruction")},
                span, STEP_WORDS,
            )
    elif request.kind is not TrollKind.FUNNY_BEAT:
        if request.kind is TrollKind.RAP_BATTLE:
            battle = battle_request_for(request.model_copy(update={"rapper_name": artist}))
            lyrics_asset = _run(context, lyrics_jobs.generate_battle, {"request": battle.model_dump(mode="json")}, (0.0, 0.3), STEP_WORDS)
        else:
            lyrics_asset = _run(context, _write_troll, {"request": request.model_dump(mode="json")}, (0.0, 0.3), STEP_WORDS)
    title = (lyrics_asset.content or {}).get("title") if lyrics_asset else None
    title = title or beat_title(request)

    # ---- 2. performance: vocals first, so the beat is cut to fit them ----
    vocals: Asset | None = None
    if lyrics_asset is not None:
        voice_b = request.voice_b or (_second_voice(context) if request.kind is TrollKind.RAP_BATTLE else None)
        section_voices = {p.name: p.voice for p in request.people if p.voice}
        vocals = _run(
            context, audio_jobs.generate_vocals,
            {"lyrics_asset_id": lyrics_asset.id, "bpm": preset_bpm, "voice": request.voice, "voice_b": voice_b,
             "section_voices": section_voices},
            (0.3, 0.55), STEP_VOCALS,
        )

    # ---- 3. beat ----
    bar = 240.0 / preset_bpm
    if vocals is not None and vocals.duration_seconds:
        seconds = min(300.0, math.ceil((vocals.duration_seconds + 3 * bar) / bar) * bar)
    else:
        seconds = round(16 * bar, 2) if 16 * bar <= 45 else round(8 * bar, 2)
    beat_request = BeatRequest(
        genre=request.beat_genre, bpm=preset_bpm, mood="playful", energy=_ENERGY[request.intensity.value],
        duration_seconds=max(5.0, seconds), description=f"funny meme beat, {request.genre}, comedic, bouncy"[:500],
    )
    beat = _run(
        context, audio_jobs.generate_beat,
        {"request": beat_request.model_dump(mode="json"), "lyrics_asset_id": lyrics_asset.id if lyrics_asset else None,
         "seed": secrets.randbelow(2**31)},
        (0.55, 0.7), STEP_BEAT,
    )

    # ---- 4. mix ----
    primary = beat
    if lyrics_asset is not None and vocals is not None:
        primary = _run(
            context, audio_jobs.generate_song,
            {"mode": "mix", "lyrics_asset_id": lyrics_asset.id, "beat_asset_id": beat.id, "vocals_asset_id": vocals.id, "title": title},
            (0.7, 0.8), STEP_MIX,
        )
    else:
        primary.title = title

    # ---- 5. extras: fake album cover, meme video ----
    cover: Asset | None = None
    if with_cover:
        try:
            cover = _run(
                context, visual_jobs.generate_artwork,
                {"title": title, "genre": request.style, "style": "meme", "artist": billing,
                 "lyrics_asset_id": lyrics_asset.id if lyrics_asset else None,
                 "notes": f"ridiculous rapper persona {artist}, comedic, exaggerated"},
                (0.8, 0.86 if with_video else 0.99), STEP_COVER,
            )
        except TrollMusicError as exc:
            warnings.append(f"No album cover: {exc.message}")

    video: Asset | None = None
    if with_video:
        video = _run(
            context, visual_jobs.generate_video,
            {"audio_asset_id": primary.id, "lyrics_asset_id": lyrics_asset.id if lyrics_asset else None, "title": title,
             "style": "meme", "aspect": "9:16", "subtitles": True, "intro": {"presenter": billing, "title": title},
             "notes": "meme music video, comedic scenes, dramatic and ridiculous"},
            (0.86, 0.99), STEP_VIDEO,
        )

    context.progress(0.995, "Done. Send it to the group chat.")
    primary.meta = {
        **(primary.meta or {}),
        "troll": {
            "kind": request.kind.value,
            "label": KIND_LABELS[request.kind],
            "artist": artist,
            "target": request.who,
            "style": request.style,
            "intensity": request.intensity.value,
            "lyrics_asset_id": lyrics_asset.id if lyrics_asset else None,
            "cover_asset_id": cover.id if cover else None,
            "video_asset_id": video.id if video else None,
            "warnings": warnings,
            "lyrics_reused": reused,
            "remix_of": context.params.get("remix_of"),
            "rivalry_id": context.params.get("rivalry_id"),
            # Everything needed to make it again or remix it.
            "request": request.model_dump(mode="json"),
            "with_video": with_video,
            "with_cover": with_cover,
        },
    }
    return (video or primary).id


def _write_troll(context: JobContext) -> str:
    """Lyrics for a diss track, roast, meme song or group roast."""
    request = TrollRequest.model_validate(context.params["request"])
    service = lyrics_jobs._service(context)
    lyrics = asyncio.run(service.generate_troll(request, on_progress=context.progress))
    params = lyrics_request_for(request).model_dump(mode="json") | {"troll": request.model_dump(mode="json")}
    return lyrics_jobs._store(context, lyrics, origin="generated", params=params)


HANDLERS: dict[str, JobHandler] = {JOB_TROLL: generate_troll}
