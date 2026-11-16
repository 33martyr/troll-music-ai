"""Voice profiles: authorized voices only.

A profile cannot be created without the voice owner's recorded consent. The
sample is stored privately and only ever served through the authenticated API.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from backend.audio import ffmpeg
from backend.core.errors import ApiError
from backend.core.storage import Storage
from backend.models.tables import VoiceProfile, new_id
from backend.services.providers import ProviderManager
from troll_music_ai import TrollMusicError
from troll_music_ai.providers import VoiceProvider

MIN_SAMPLE_SECONDS = 5.0
MAX_SAMPLE_SECONDS = 300.0


def save_upload(stream: BinaryIO, target: Path, max_bytes: int) -> int:
    """Copy an upload to disk, refusing anything over the size limit."""
    written = 0
    with target.open("wb") as out:
        while chunk := stream.read(1024 * 1024):
            written += len(chunk)
            if written > max_bytes:
                raise ApiError(413, "file_too_large", f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
            out.write(chunk)
    if written == 0:
        raise ApiError(422, "invalid_media", "The uploaded file is empty.")
    return written


def create_profile(
    session: Session,
    storage: Storage,
    providers: ProviderManager,
    *,
    name: str,
    owner_name: str,
    consent_confirmed: bool,
    consent_statement: str,
    stream: BinaryIO,
    max_bytes: int,
) -> VoiceProfile:
    name, owner_name, consent_statement = name.strip(), owner_name.strip(), consent_statement.strip()
    if not consent_confirmed or len(owner_name) < 2 or len(consent_statement) < 10:
        raise ApiError(
            422,
            "consent_required",
            "A voice profile needs the voice owner's explicit consent: their name, a consent "
            "statement and the confirmation box.",
        )
    if not name:
        raise ApiError(422, "validation_error", "Give the voice profile a name.")

    workdir = Path(tempfile.mkdtemp(prefix="troll-voice-"))
    profile_id = new_id()
    key = f"voices/{profile_id}.wav"
    try:
        raw = workdir / "upload"
        save_upload(stream, raw, max_bytes)
        info = ffmpeg.probe(raw)  # raises InvalidMediaError for non-audio
        if not info.has_audio:
            raise ApiError(422, "invalid_media", "That file has no audio in it.")
        if not MIN_SAMPLE_SECONDS <= info.duration <= MAX_SAMPLE_SECONDS:
            raise ApiError(
                422,
                "invalid_media",
                f"The sample must be between {MIN_SAMPLE_SECONDS:.0f} seconds and "
                f"{MAX_SAMPLE_SECONDS / 60:.0f} minutes long (this one is {info.duration:.1f} s).",
            )
        wav = ffmpeg.to_wav(raw, workdir / "sample.wav", channels=1)
        volume = ffmpeg.mean_volume_db(wav)
        warnings = []
        if volume is not None and volume < -35:
            warnings.append("The recording is very quiet; cloning quality will suffer.")
        if info.duration < 15:
            warnings.append("Short sample: 30 seconds or more of clean speech clones better.")
        storage.save(wav, key)

        provider: VoiceProvider | None = providers.get("voice")  # type: ignore[assignment]
        provider_name = provider_voice_id = None
        if provider is not None and provider.capabilities.cloning:
            try:
                provider_voice_id = asyncio.run(provider.create_voice(name, storage.path(key)))
            except TrollMusicError:
                storage.delete(key)
                raise
            provider_name = provider.info.name
        profile = VoiceProfile(
            id=profile_id,
            name=name[:120],
            owner_name=owner_name[:120],
            consent_statement=consent_statement[:1000],
            sample_storage_key=key,
            provider=provider_name,
            provider_voice_id=provider_voice_id,
            meta={
                "duration_seconds": round(info.duration, 2),
                "sample_rate": info.sample_rate,
                "mean_volume_db": volume,
                "warnings": warnings,
            },
        )
        session.add(profile)
        session.flush()
        return profile
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def delete_profile(session: Session, storage: Storage, providers: ProviderManager, profile: VoiceProfile) -> str:
    """Delete the profile, its sample and the provider's copy of the voice.

    Returns a note when the provider's copy could not be removed.
    """
    note = ""
    if profile.provider and profile.provider_voice_id:
        provider: VoiceProvider | None = providers.get("voice")  # type: ignore[assignment]
        if provider is not None and provider.info.name == profile.provider:
            try:
                asyncio.run(provider.delete_voice(profile.provider_voice_id))
            except (TrollMusicError, NotImplementedError) as exc:
                note = f"The voice could not be removed from {profile.provider}: {getattr(exc, 'message', 'not supported')}"
        else:
            note = f"{profile.provider} is no longer the active voice provider, so its copy of the voice was not removed."
    storage.delete(profile.sample_storage_key)
    session.delete(profile)
    session.flush()
    return note
