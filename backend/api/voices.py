"""Voice profiles (authorized voices only) and the provider's stock voices."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.api.deps import ProvidersDep, SessionDep, SettingsDep, StorageDep
from backend.core.errors import not_found
from backend.models.schemas import StockVoicesOut, VoiceProfileOut
from backend.models.tables import VoiceProfile
from backend.services import voices as voice_service
from troll_music_ai import TrollMusicError

router = APIRouter(prefix="/api/voices", tags=["voices"])


@router.get("", response_model=list[VoiceProfileOut])
def list_profiles(session: SessionDep):
    return list(session.scalars(select(VoiceProfile).order_by(VoiceProfile.created_at.desc())))


@router.get("/stock", response_model=StockVoicesOut)
def stock_voices(providers: ProvidersDep):
    """Voices the active provider offers without a profile, and what it can do."""
    provider = providers.get("voice")
    if provider is None:
        return StockVoicesOut(provider=None, note=providers.error("voice") or "No voice provider is configured.")
    info, capabilities = provider.info, provider.capabilities  # type: ignore[attr-defined]
    note = ""
    try:
        names = asyncio.run(provider.voices())  # type: ignore[attr-defined]
    except TrollMusicError as exc:
        names, note = [], exc.message
    if not capabilities.singing:
        note = (note + " " if note else "") + "This provider speaks lines in rhythm; it does not sing."
    return StockVoicesOut(
        provider=info.name, model=info.model, is_ai=info.is_ai, voices=names, note=note,
        **capabilities.model_dump(),
    )


@router.post("", response_model=VoiceProfileOut, status_code=201)
def create_profile(
    session: SessionDep,
    storage: StorageDep,
    providers: ProvidersDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form()],
    owner_name: Annotated[str, Form()] = "",
    consent_statement: Annotated[str, Form()] = "",
    consent_confirmed: Annotated[bool, Form()] = False,
):
    """Create a profile from a recording. Rejected without the owner's consent."""
    profile = voice_service.create_profile(
        session, storage, providers,
        name=name, owner_name=owner_name, consent_confirmed=consent_confirmed,
        consent_statement=consent_statement, stream=file.file,
        max_bytes=settings.max_upload_mb * 1024 * 1024,
    )
    session.commit()
    return profile


@router.delete("/{profile_id}")
def delete_profile(profile_id: str, session: SessionDep, storage: StorageDep, providers: ProvidersDep):
    """Remove the profile, its private sample and the provider's copy."""
    profile = session.get(VoiceProfile, profile_id)
    if profile is None:
        raise not_found("Voice profile")
    note = voice_service.delete_profile(session, storage, providers, profile)
    session.commit()
    return {"deleted": True, "note": note}


@router.get("/{file_id}/sample")
def profile_sample(file_id: str, session: SessionDep, storage: StorageDep):
    """The private sample. Only reachable with the API key or its signed token."""
    profile = session.get(VoiceProfile, file_id)
    if profile is None or not storage.exists(profile.sample_storage_key):
        raise not_found("Voice sample")
    return FileResponse(
        storage.path(profile.sample_storage_key), media_type="audio/wav",
        content_disposition_type="inline", headers={"Cache-Control": "private, no-store"},
    )
