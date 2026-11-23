"""Beat, vocal, voice-conversion and song job handlers.

Every stage is its own job with its own output asset. A song job reads the
lyrics, beat and vocals it is given and never regenerates them: only a missing
vocal track is created, and it is stored as a separate asset.
"""

from __future__ import annotations

import asyncio
import math
import secrets
from pathlib import Path

from backend.audio import ffmpeg
from backend.audio.vocals import VocalLine, build_vocal_track
from backend.models.tables import Asset, AssetKind, VoiceProfile
from backend.workers.runner import JobContext, JobHandler
from troll_music_ai import FeatureNotAvailableError, Lyrics, TrollMusicError
from troll_music_ai.providers import MusicGenerationProvider, VoiceProvider
from troll_music_ai.providers.procedural import preset_for
from troll_music_ai.types import BeatRequest, SongRequest, SpeechLine

JOB_BEAT = "beat.generate"
JOB_VOCALS = "vocals.generate"
JOB_CONVERT = "vocals.convert"
JOB_SONG = "song.generate"

AUDIO_KINDS = (AssetKind.BEAT, AssetKind.VOCALS, AssetKind.SONG)


# --------------------------------- beats ---------------------------------- #


def generate_beat(context: JobContext) -> str:
    request = BeatRequest.model_validate(context.params["request"])
    provider: MusicGenerationProvider = context.providers.require("music")  # type: ignore[assignment]
    info = context.using(provider)
    capabilities = provider.capabilities
    lyrics = context.asset(context.params["lyrics_asset_id"], AssetKind.LYRICS) if context.params.get("lyrics_asset_id") else None

    seed = context.params.get("seed") or secrets.randbelow(2**31)
    looped = bool(capabilities.max_duration_seconds and request.duration_seconds > capabilities.max_duration_seconds)
    bpm = request.bpm or (preset_for(request.genre)["bpm"] if capabilities.exact_bpm else None)
    first_id = ""
    for index in range(request.variations):
        label = f"variation {index + 1} of {request.variations}" if request.variations > 1 else "the beat"
        context.progress(index / request.variations, f"Generating {label} with {info.name}")
        raw = asyncio.run(provider.generate_instrumental(request, context.workdir / f"raw_{index}", seed + index))
        context.progress((index + 0.7) / request.variations, "Normalizing and encoding")
        final = ffmpeg.finalize_audio(
            raw, context.workdir / f"beat_{index}.mp3", duration=request.duration_seconds, loop=looped
        )
        suffix = f" #{index + 1}" if request.variations > 1 else ""
        asset = context.store(
            final,
            kind=AssetKind.BEAT,
            title=f"{request.genre.title()} beat{f' · {bpm} BPM' if bpm else ''}{suffix}",
            info=info,
            mime_type="audio/mpeg",
            duration=ffmpeg.probe(final).duration,
            meta={
                "bpm": bpm,
                # False means the tempo was only requested in the prompt, not guaranteed.
                "bpm_exact": capabilities.exact_bpm,
                "genre": request.genre,
                "mood": request.mood,
                "key": request.key,
                "seed": seed + index,
                "looped": looped,
            },
            sources={"lyrics": lyrics},
            params=request.model_dump(mode="json"),
        )
        first_id = first_id or asset.id
    return first_id


# --------------------------------- vocals --------------------------------- #


def _vocal_lines(lyrics: Lyrics) -> list[tuple[str, str, str | None, str]]:
    return [
        (section.id, section.label, section.performer, line)
        for section in lyrics.sections
        for line in section.lines
    ]


def _make_vocals(context: JobContext, lyrics_asset: Asset, bpm: float, span: tuple[float, float]) -> Asset:
    """Synthesize and place the vocal track; store it as its own asset."""
    provider: VoiceProvider = context.providers.require("voice")  # type: ignore[assignment]
    info = context.using(provider)
    params = context.params
    lyrics = Lyrics.model_validate(lyrics_asset.content)
    rows = _vocal_lines(lyrics)
    if not rows:
        raise TrollMusicError("These lyrics have no lines to perform.")

    voice, sample = params.get("voice"), None
    profile = None
    if params.get("voice_profile_id"):
        profile = context.session.get(VoiceProfile, params["voice_profile_id"])
        if profile is None:
            raise TrollMusicError("That voice profile no longer exists.")
        if not provider.capabilities.cloning:
            raise FeatureNotAvailableError(
                f"The active voice provider ({info.name}) cannot use voice profiles. "
                "Choose a cloning provider such as ElevenLabs or Chatterbox in Model Settings."
            )
        if profile.provider != info.name or not profile.provider_voice_id:
            raise TrollMusicError(
                f"This voice profile was not registered with {info.name}. Delete it and create it again."
            )
        voice, sample = profile.provider_voice_id, str(context.storage.path(profile.sample_storage_key))

    # In a battle, character B gets the second voice. Prefer the name from the
    # battle request; otherwise the second performer to appear.
    performers = [p for p in dict.fromkeys(row[2] for row in rows) if p]
    character_b = ((lyrics_asset.params or {}).get("character_b") or {}).get("name")
    second = character_b if character_b in performers else (performers[1] if len(performers) > 1 else None)
    voice_b = params.get("voice_b")
    # Group chat roasts: each person's section in their own voice, where given.
    by_section = {k: v for k, v in (params.get("section_voices") or {}).items() if v} if not sample else {}

    def voice_for(label: str, performer: str | None) -> str | None:
        if label in by_section:
            return by_section[label]
        return voice_b if voice_b and second and performer == second else voice

    lines = [SpeechLine(text=text, voice=voice_for(label, performer), sample_path=sample) for _, label, performer, text in rows]

    start, end = span
    context.progress(start, f"Performing {len(lines)} lines with {info.name}")
    speech_dir = context.workdir / "speech"
    speech_dir.mkdir(exist_ok=True)
    files = asyncio.run(provider.synthesize_lines(lines, speech_dir))
    context.progress(start + (end - start) * 0.6, "Placing lines on the beat grid")
    vocal_lines = [
        VocalLine(section_id, label, performer, text, path)
        for (section_id, label, performer, text), path in zip(rows, files)
    ]
    wav = context.workdir / "vocals.wav"
    timings, duration = build_vocal_track(vocal_lines, bpm, wav, context.workdir)
    final = ffmpeg.finalize_audio(wav, context.workdir / "vocals.mp3", normalize=False, fade_out=0)
    return context.store(
        final,
        kind=AssetKind.VOCALS,
        title=f"{lyrics.title} · vocals",
        info=info,
        mime_type="audio/mpeg",
        duration=duration,
        meta={
            "bpm": bpm,
            # Honest label: every voice provider today speaks; none of them sings.
            "delivery": "sung" if provider.capabilities.singing else "spoken",
            "voice": profile.name if profile else voice,
            "voice_profile_id": profile.id if profile else None,
            "line_timings": timings,
        },
        sources={"lyrics": lyrics_asset},
    )


def _bpm_for(context: JobContext, lyrics_asset: Asset, beat: Asset | None) -> float:
    candidates = [
        context.params.get("bpm"),
        (beat.meta or {}).get("bpm") if beat else None,
        (lyrics_asset.content or {}).get("suggested_bpm"),
    ]
    return float(next((value for value in candidates if value), 120))


def generate_vocals(context: JobContext) -> str:
    lyrics_asset = context.asset(context.params["lyrics_asset_id"], AssetKind.LYRICS)
    beat = context.asset(context.params["beat_asset_id"], AssetKind.BEAT) if context.params.get("beat_asset_id") else None
    return _make_vocals(context, lyrics_asset, _bpm_for(context, lyrics_asset, beat), (0.05, 0.9)).id


def convert_vocals(context: JobContext) -> str:
    """Re-voice an existing vocal recording with an authorized voice profile."""
    source = context.asset(context.params["source_asset_id"], AUDIO_KINDS)
    profile = context.session.get(VoiceProfile, context.params["voice_profile_id"])
    if profile is None:
        raise TrollMusicError("That voice profile no longer exists.")
    provider: VoiceProvider = context.providers.require("voice")  # type: ignore[assignment]
    info = context.using(provider)
    if not provider.capabilities.conversion:
        raise FeatureNotAvailableError(
            f"The active voice provider ({info.name}) cannot convert vocals. "
            "ElevenLabs supports this; choose it in Model Settings."
        )
    if profile.provider != info.name or not profile.provider_voice_id:
        raise TrollMusicError(f"This voice profile was not registered with {info.name}.")
    context.progress(0.1, f"Converting the vocal with {info.name}")
    raw = asyncio.run(provider.convert_voice(context.file_of(source), profile.provider_voice_id, context.workdir / "converted"))
    final = ffmpeg.finalize_audio(raw, context.workdir / "converted_final.mp3", normalize=False, fade_out=0)
    return context.store(
        final,
        kind=AssetKind.VOCALS,
        title=f"{source.title} · {profile.name}",
        info=info,
        mime_type="audio/mpeg",
        duration=ffmpeg.probe(final).duration,
        # Conversion keeps the source timing, so its line timings still apply.
        meta={**(source.meta or {}), "voice": profile.name, "voice_profile_id": profile.id},
        origin="converted",
        sources={"source_vocal": source},
    ).id


# ---------------------------------- songs --------------------------------- #


def _lyrics_text(lyrics: Lyrics) -> str:
    return "\n\n".join("\n".join([f"[{s.label}]", *s.lines]) for s in lyrics.sections)


def _song_from_model(context: JobContext, lyrics_asset: Asset) -> str:
    """Let a music model that can sing produce the whole song from the lyrics."""
    provider: MusicGenerationProvider = context.providers.require("music")  # type: ignore[assignment]
    info = context.using(provider)
    if not provider.capabilities.with_vocals:
        raise FeatureNotAvailableError(
            f"The active music provider ({info.name}) cannot sing lyrics. "
            "ACE-Step can; choose it in Model Settings, or mix a beat with spoken vocals instead."
        )
    lyrics = Lyrics.model_validate(lyrics_asset.content)
    request = SongRequest(
        lyrics_text=_lyrics_text(lyrics),
        style_prompt=context.params.get("style_prompt") or f"{lyrics.suggested_genre or 'hip-hop'}, comedic rap vocals",
        duration_seconds=float(context.params.get("duration_seconds") or 90),
        bpm=lyrics.suggested_bpm,
    )
    context.progress(0.05, f"Generating the full song with {info.name}")
    raw = asyncio.run(provider.generate_song(request, context.workdir / "song_raw", secrets.randbelow(2**31)))
    context.progress(0.85, "Normalizing and encoding")
    final = ffmpeg.finalize_audio(raw, context.workdir / "song.mp3")
    return context.store(
        final,
        kind=AssetKind.SONG,
        title=context.params.get("title") or lyrics.title,
        info=info,
        mime_type="audio/mpeg",
        duration=ffmpeg.probe(final).duration,
        meta={"bpm": lyrics.suggested_bpm, "delivery": "sung", "mode": "model"},
        sources={"lyrics": lyrics_asset},
    ).id


def generate_song(context: JobContext) -> str:
    params = context.params
    lyrics_asset = context.asset(params["lyrics_asset_id"], AssetKind.LYRICS)
    if params.get("mode") == "model":
        return _song_from_model(context, lyrics_asset)

    beat = context.asset(params["beat_asset_id"], AssetKind.BEAT)
    bpm = _bpm_for(context, lyrics_asset, beat)
    if params.get("vocals_asset_id"):
        vocals = context.asset(params["vocals_asset_id"], AssetKind.VOCALS)
    else:
        vocals = _make_vocals(context, lyrics_asset, bpm, (0.05, 0.6))

    context.progress(0.7, "Mixing vocals and beat")
    bar = 240.0 / bpm
    vocal_seconds = vocals.duration_seconds or ffmpeg.probe(context.file_of(vocals)).duration
    duration = math.ceil((vocal_seconds + 2 * bar) / bar) * bar  # two bars of outro, ending on a bar line
    final = ffmpeg.mix(
        context.file_of(beat),
        context.file_of(vocals),
        context.workdir / "song.mp3",
        duration=duration,
        vocal_gain_db=float(params.get("vocal_gain_db", 3.0)),
        beat_gain_db=float(params.get("beat_gain_db", -4.0)),
    )
    context.progress(0.95, "Saving")
    lyrics_title = (lyrics_asset.content or {}).get("title") or lyrics_asset.title
    vocal_meta = vocals.meta or {}
    song = context.store(
        Path(final),
        kind=AssetKind.SONG,
        title=params.get("title") or lyrics_title,
        # The mix itself is FFmpeg; the creative work is in the source assets.
        info=None,
        mime_type="audio/mpeg",
        duration=ffmpeg.probe(final).duration,
        meta={
            "bpm": bpm,
            "mode": "mix",
            "delivery": vocal_meta.get("delivery"),
            "line_timings": vocal_meta.get("line_timings"),
            "made_with": {"beat": beat.provider, "vocals": vocals.provider, "lyrics": lyrics_asset.provider},
        },
        sources={"lyrics": lyrics_asset, "beat": beat, "vocals": vocals},
    )
    song.provider, song.model = "ffmpeg-mix", None
    song.is_ai = bool(beat.is_ai or vocals.is_ai or lyrics_asset.is_ai)
    return song.id


HANDLERS: dict[str, JobHandler] = {
    JOB_BEAT: generate_beat,
    JOB_VOCALS: generate_vocals,
    JOB_CONVERT: convert_vocals,
    JOB_SONG: generate_song,
}
