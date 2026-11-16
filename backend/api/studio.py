"""Beat, vocal, song, video and artwork generation endpoints.

Each one validates its inputs, checks that the provider it needs is
configured, and answers ``202 Accepted`` with a job.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import ProvidersDep, QueueDep, SessionDep, load_asset, submit_job
from backend.audio import ffmpeg
from backend.core.errors import ApiError, not_found
from backend.models.schemas import (
    ConvertVocalsBody,
    GenerateArtworkBody,
    GenerateBeatBody,
    GenerateSongBody,
    GenerateVideoBody,
    GenerateVocalsBody,
    JobOut,
)
from backend.models.tables import AssetKind, VoiceProfile
from backend.services import audio_jobs, visual_jobs
from troll_music_ai import FeatureNotAvailableError

router = APIRouter(prefix="/api", tags=["studio"])


def _require_ffmpeg() -> None:
    ok, detail = ffmpeg.available()
    if not ok:
        raise ApiError(503, "ffmpeg_missing", f"FFmpeg is required for audio and video processing. {detail}")


def _check_profile(session, providers, profile_id: str | None) -> None:
    """A voice profile only works with a provider that can clone voices."""
    if not profile_id:
        return
    if session.get(VoiceProfile, profile_id) is None:
        raise not_found("Voice profile")
    provider = providers.require("voice")
    if not provider.capabilities.cloning:  # type: ignore[attr-defined]
        raise FeatureNotAvailableError(
            f"The active voice provider ({provider.info.name}) cannot use voice profiles. "
            "Choose a cloning provider such as ElevenLabs or Chatterbox in Model Settings."
        )


def _params(body, *exclude: str) -> dict:
    return body.model_dump(mode="json", exclude={"project_id", *exclude})


@router.post("/beats/generate", response_model=JobOut, status_code=202)
def generate_beat(body: GenerateBeatBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    providers.require("music")
    _require_ffmpeg()
    if body.lyrics_asset_id:
        load_asset(session, body.lyrics_asset_id, AssetKind.LYRICS)
    return submit_job(session, queue, kind=audio_jobs.JOB_BEAT, project_id=body.project_id, params=_params(body))


@router.post("/vocals/generate", response_model=JobOut, status_code=202)
def generate_vocals(body: GenerateVocalsBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    """Perform lyrics as a vocal track. Voice providers speak; the lines are
    placed on the beat grid. See ``delivery`` in the result's ``meta``."""
    providers.require("voice")
    _require_ffmpeg()
    lyrics = load_asset(session, body.lyrics_asset_id, AssetKind.LYRICS)
    if body.beat_asset_id:
        load_asset(session, body.beat_asset_id, AssetKind.BEAT)
    _check_profile(session, providers, body.voice_profile_id)
    return submit_job(
        session, queue, kind=audio_jobs.JOB_VOCALS, project_id=body.project_id or lyrics.project_id, params=_params(body)
    )


@router.post("/vocals/convert", response_model=JobOut, status_code=202)
def convert_vocals(body: ConvertVocalsBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    """Re-voice an existing vocal with an authorized voice profile."""
    provider = providers.require("voice")
    source = load_asset(session, body.source_asset_id, audio_jobs.AUDIO_KINDS)
    if session.get(VoiceProfile, body.voice_profile_id) is None:
        raise not_found("Voice profile")
    if not provider.capabilities.conversion:  # type: ignore[attr-defined]
        raise FeatureNotAvailableError(
            f"The active voice provider ({provider.info.name}) cannot convert vocals. "
            "ElevenLabs supports this; choose it in Model Settings."
        )
    return submit_job(
        session, queue, kind=audio_jobs.JOB_CONVERT, project_id=body.project_id or source.project_id, params=_params(body)
    )


@router.post("/songs/generate", response_model=JobOut, status_code=202)
def generate_song(body: GenerateSongBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    _require_ffmpeg()
    lyrics = load_asset(session, body.lyrics_asset_id, AssetKind.LYRICS)
    if body.mode == "model":
        provider = providers.require("music")
        if not provider.capabilities.with_vocals:  # type: ignore[attr-defined]
            raise FeatureNotAvailableError(
                f"The active music provider ({provider.info.name}) cannot sing lyrics. "
                "ACE-Step can; choose it in Model Settings, or use mix mode."
            )
    else:
        if not body.beat_asset_id:
            raise ApiError(422, "validation_error", "Choose a beat to mix the vocals over.")
        load_asset(session, body.beat_asset_id, AssetKind.BEAT)
        if body.vocals_asset_id:
            load_asset(session, body.vocals_asset_id, AssetKind.VOCALS)
        else:
            providers.require("voice")
            _check_profile(session, providers, body.voice_profile_id)
    return submit_job(
        session, queue, kind=audio_jobs.JOB_SONG, project_id=body.project_id or lyrics.project_id, params=_params(body)
    )


@router.post("/videos/generate", response_model=JobOut, status_code=202)
def generate_video(body: GenerateVideoBody, session: SessionDep, queue: QueueDep):
    """Render an MP4 from scene images with FFmpeg. Needs audio or lyrics."""
    _require_ffmpeg()
    if not body.audio_asset_id and not body.lyrics_asset_id:
        raise ApiError(422, "validation_error", "Choose a song (or other audio) or lyrics to make a video from.")
    project_id = body.project_id
    if body.audio_asset_id:
        project_id = project_id or load_asset(session, body.audio_asset_id, visual_jobs.AUDIO_KINDS).project_id
    if body.lyrics_asset_id:
        project_id = project_id or load_asset(session, body.lyrics_asset_id, AssetKind.LYRICS).project_id
    return submit_job(session, queue, kind=visual_jobs.JOB_VIDEO, project_id=project_id, params=_params(body))


@router.post("/artwork/generate", response_model=JobOut, status_code=202)
def generate_artwork(body: GenerateArtworkBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    providers.require("image")
    if body.lyrics_asset_id:
        load_asset(session, body.lyrics_asset_id, AssetKind.LYRICS)
    return submit_job(session, queue, kind=visual_jobs.JOB_ARTWORK, project_id=body.project_id, params=_params(body))
