"""Provider status, Model Settings, hardware and the option lists the UI renders."""

from __future__ import annotations

import importlib.util
import platform
import subprocess
import sys

from fastapi import APIRouter

from backend.api.deps import ProvidersDep, SessionDep, SettingsDep
from backend.audio import ffmpeg
from backend.core.errors import ApiError
from backend.models.schemas import (
    CapabilityOut,
    ProviderCheckOut,
    ProviderOptionOut,
    ProviderStateOut,
    ProviderUpdate,
)
from backend.models.tables import ProviderSetting
from backend.services.providers import KINDS, LABELS, ProviderManager
from backend.video.render import SIZES
from troll_music_ai import TrollMusicError, types
from troll_music_ai.providers import ProviderConfig, ProviderKind, registry

router = APIRouter(prefix="/api", tags=["system"])


def _check_kind(kind: str) -> None:
    if kind not in KINDS:
        raise ApiError(404, "not_found", f"Unknown provider kind. Use one of: {', '.join(KINDS)}.")


@router.get("/system/capabilities", response_model=list[CapabilityOut])
def capabilities(providers: ProvidersDep):
    """One line per capability: what is serving it right now."""
    out = []
    for kind in KINDS:
        provider = providers.get(kind)
        item = CapabilityOut(kind=kind, label=LABELS[kind], implemented=True, configured=provider is not None)
        if provider is None:
            item.note = providers.error(kind) or "Not configured. Choose a provider in Model Settings."
        else:
            info = provider.info
            item.provider, item.model, item.endpoint = info.name, info.model, info.endpoint
            item.is_mock, item.is_ai = info.is_mock, info.is_ai
            if info.is_mock:
                item.note = "Mock provider: output is placeholder text, not AI-generated."
            elif not info.is_ai:
                item.note = "Built-in engine: real output, but not an AI model."
        out.append(item)
    out.append(
        CapabilityOut(
            kind="video", label="Video animation", implemented=False, configured=False, is_ai=False,
            note="No AI video model is integrated. Videos are rendered from still images with FFmpeg.",
        )
    )
    return out


def _state(providers: ProviderManager, kind: str, session) -> ProviderStateOut:
    config = providers.config(kind)
    provider = providers.get(kind)
    row = session.get(ProviderSetting, kind)
    info = provider.info if provider else None
    return ProviderStateOut(
        kind=kind,
        label=LABELS[kind],
        source=providers.source(kind),
        provider=info.name if info else (row.provider if row else config.provider),
        model=info.model if info else config.model,
        base_url=(info.endpoint if info else None) or config.base_url,
        has_api_key=bool(config.api_key),
        enabled=row.enabled if row else True,
        configured=provider is not None,
        error=providers.error(kind),
        is_ai=bool(info and info.is_ai),
        is_mock=bool(info and info.is_mock),
        options=[
            ProviderOptionOut(
                name=spec.name, label=spec.label, description=spec.description, local=spec.local,
                is_ai=spec.is_ai, is_mock=spec.is_mock, needs_api_key=spec.needs_api_key,
                needs_base_url=spec.needs_base_url, needs_model=spec.needs_model,
                default_base_url=spec.default_base_url, default_model=spec.default_model,
                suggested_models=list(spec.suggested_models), capabilities=list(spec.capabilities),
                params=list(spec.params), hardware=spec.hardware, license=spec.license,
                commercial_use=spec.commercial_use, setup=spec.setup, verified=spec.verified,
                missing_packages=spec.missing_packages(),
            )
            for spec in registry.specs(ProviderKind(kind))
        ],
    )


@router.get("/system/providers", response_model=list[ProviderStateOut])
def list_providers(providers: ProvidersDep, session: SessionDep):
    """Everything Model Settings shows. API keys are never included."""
    return [_state(providers, kind, session) for kind in KINDS]


@router.put("/system/providers/{kind}", response_model=ProviderStateOut)
def update_provider(kind: str, body: ProviderUpdate, providers: ProvidersDep, session: SessionDep, settings: SettingsDep):
    """Choose the provider and model for one capability. Takes effect at once.

    The configuration is validated first, so a provider that cannot work
    (missing key, missing package) is rejected instead of saved.
    """
    _check_kind(kind)
    name = body.provider.strip().lower()
    row = session.get(ProviderSetting, kind)
    if body.api_key is None:  # keep the stored key, but never carry it to a different provider
        api_key = row.api_key if row and row.provider == name else None
    else:
        api_key = body.api_key.strip() or None
    env = settings.provider_config(kind)
    candidate = ProviderConfig(
        provider=name,
        model=(body.model or "").strip() or None,
        base_url=(body.base_url or "").strip() or None,
        api_key=api_key or (env.api_key if env.provider == name else None),
        options=env.options,
    )
    if name != "none" and body.enabled:
        try:
            registry.build(ProviderKind(kind), candidate)
        except TrollMusicError as exc:
            raise ApiError(422, "provider_not_configured", exc.message) from exc
    if row is None:
        row = ProviderSetting(kind=kind, provider=name)
        session.add(row)
    row.provider, row.model, row.base_url = name, candidate.model, candidate.base_url
    row.api_key, row.enabled = api_key, body.enabled
    session.commit()
    providers.invalidate(kind)
    return _state(providers, kind, session)


@router.delete("/system/providers/{kind}", response_model=ProviderStateOut)
def reset_provider(kind: str, providers: ProvidersDep, session: SessionDep):
    """Forget the Model Settings choice (and its stored key); use the environment."""
    _check_kind(kind)
    row = session.get(ProviderSetting, kind)
    if row is not None:
        session.delete(row)
        session.commit()
    providers.invalidate(kind)
    return _state(providers, kind, session)


@router.post("/system/providers/{kind}/check", response_model=ProviderCheckOut)
async def check_provider(kind: str, providers: ProvidersDep):
    """Live connectivity check against the active provider."""
    _check_kind(kind)
    provider = providers.get(kind)
    if provider is None:
        return ProviderCheckOut(ok=False, detail=providers.error(kind) or f"No {LABELS[kind].lower()} provider is configured.")
    status = await provider.check()
    return ProviderCheckOut(ok=status.ok, detail=status.detail, models=status.models[:50])


@router.post("/system/capabilities/text/check", response_model=ProviderCheckOut, include_in_schema=False)
async def check_text_provider(providers: ProvidersDep):
    return await check_provider("text", providers)


def _gpus() -> list[dict]:
    try:
        done = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in done.stdout.splitlines() if done.returncode == 0 else []:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 3 and parts[1].isdigit():
            gpus.append({"name": parts[0], "memory_total_mb": int(parts[1]), "memory_used_mb": int(parts[2]) if parts[2].isdigit() else None})
    return gpus


@router.get("/system/hardware")
def hardware():
    """What this machine offers for local models. Does not load any model."""
    ffmpeg_ok, ffmpeg_detail = ffmpeg.available()
    packages = {name: importlib.util.find_spec(name) is not None for name in ("torch", "transformers", "numpy", "PIL", "pyttsx3", "chatterbox")}
    return {
        "platform": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "ffmpeg": {"ok": ffmpeg_ok, "detail": ffmpeg_detail},
        "gpus": _gpus(),
        "packages": packages,
    }


def _lyrics_options() -> dict:
    return {
        "styles": [s.value for s in types.LyricStyle],
        "genres": list(types.GENRES),
        "moods": list(types.MOODS),
        "lengths": [s.value for s in types.SongLength],
        "chorus_styles": [s.value for s in types.ChorusStyle],
        "rhyme_complexities": [s.value for s in types.RhymeComplexity],
        "rhyme_schemes": list(types.RHYME_SCHEMES),
        "rewrite_modes": [s.value for s in types.RewriteMode],
    }


@router.get("/meta/lyrics-options")
def lyrics_options():
    return _lyrics_options()


@router.get("/meta/options")
def options(settings: SettingsDep):
    return {
        **_lyrics_options(),
        "instruments": list(types.INSTRUMENTS),
        "visual_styles": list(types.VISUAL_STYLES),
        "aspects": list(SIZES),
        "max_upload_mb": settings.max_upload_mb,
    }
