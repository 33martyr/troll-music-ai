"""REST client for a running TROLL-MUSIC-AI backend.

    from troll_music_ai import TrollMusic

    client = TrollMusic(api_key="your-api-key", base_url="http://localhost:8000")
    lyrics = client.generate_lyrics("my landlord", genre="drill")
    beat = client.generate_beat(genre="drill", bpm=140, duration_seconds=30)
    song = client.generate_song(lyrics, beat)
    client.download(song, "song.mp3")

Generation methods submit a job, wait for it and return the finished
:class:`Asset`. Pass ``wait=False`` to get the :class:`JobInfo` straight away.
:class:`AsyncTrollMusicClient` has the same methods as coroutines.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .errors import ProviderUnavailableError, TrollMusicError
from .types import BattleCharacter, Lyrics

DEFAULT_BASE_URL = "http://localhost:8000"


# -------------------------------- errors ----------------------------------- #


class ApiError(TrollMusicError):
    """The backend answered with an error. ``code`` is the backend's error code."""

    def __init__(self, message: str, *, status_code: int, code: str = "api_error") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class AuthenticationError(ApiError):
    """The backend needs an API key, or the one supplied is wrong."""


class JobFailedError(TrollMusicError):
    """A generation job failed or was cancelled. ``job`` has the details."""

    code = "job_failed"

    def __init__(self, job: "JobInfo") -> None:
        super().__init__(job.error or f"The job was {job.status}.")
        self.job = job
        self.code = job.error_code or "job_failed"


class JobTimeoutError(TrollMusicError):
    """The job was still running when the wait timed out. It keeps running."""

    code = "job_timeout"

    def __init__(self, job: "JobInfo", timeout: float) -> None:
        super().__init__(f"The job did not finish within {timeout:.0f} s (stage: {job.stage}).")
        self.job = job


# -------------------------------- models ----------------------------------- #


class _Model(BaseModel):
    model_config = {"extra": "ignore"}


class Project(_Model):
    id: str
    name: str
    description: str = ""
    asset_counts: dict[str, int] = Field(default_factory=dict)


class JobInfo(_Model):
    id: str
    kind: str
    status: str  # queued | processing | completed | failed | cancelled
    progress: float = 0.0
    stage: str = ""
    provider: str | None = None
    model: str | None = None
    result_asset_id: str | None = None
    result_asset_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error: str | None = None

    @property
    def finished(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")


class Asset(_Model):
    id: str
    kind: str  # lyrics | beat | vocals | song | video | artwork | storyboard
    title: str
    project_id: str | None = None
    content: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    duration_seconds: float | None = None
    provider: str | None = None
    model: str | None = None
    is_mock: bool = False  # placeholder output from a mock provider
    is_ai: bool = True  # False for built-in engines and uploads
    origin: str = "generated"
    version: int = 1
    has_file: bool = False
    created_at: datetime | None = None
    job: JobInfo | None = Field(default=None, exclude=True)  # the job that made it

    @property
    def lyrics(self) -> Lyrics:
        """The structured lyrics, for assets of kind ``lyrics``."""
        if self.kind != "lyrics" or not self.content:
            raise ValueError(f"This is a {self.kind} asset, not lyrics.")
        return Lyrics.model_validate(self.content)


class VoiceProfile(_Model):
    id: str
    name: str
    owner_name: str
    consent_statement: str
    provider: str | None = None
    usable: bool = False
    meta: dict[str, Any] | None = None


class ProviderState(_Model):
    kind: str
    label: str
    provider: str
    model: str | None = None
    configured: bool = False
    is_ai: bool = False
    is_mock: bool = False
    source: str = ""
    error: str = ""


def _id(value: "Asset | VoiceProfile | Project | JobInfo | str | None") -> str | None:
    return value if value is None or isinstance(value, str) else value.id


ProgressCallback = Callable[[JobInfo], None]


# ----------------------------- async client -------------------------------- #


class AsyncTrollMusicClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("TROLL_API_URL") or DEFAULT_BASE_URL).rstrip("/")
        api_key = api_key or os.environ.get("TROLL_API_KEY") or None
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=timeout, transport=transport)
        self._poll_interval = poll_interval

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncTrollMusicClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    # ------------------------------ plumbing ------------------------------- #

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.is_success:
            return
        code, message = "api_error", f"The backend answered HTTP {response.status_code}."
        try:
            error = response.json()["error"]
            code, message = error["code"], error["message"]
        except (ValueError, KeyError, TypeError):
            pass
        kind = AuthenticationError if response.status_code == 401 else ApiError
        raise kind(message, status_code=response.status_code, code=code)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"Could not reach the TROLL-MUSIC-AI backend at {self.base_url} ({type(exc).__name__}). Is it running?"
            ) from exc
        self._raise(response)
        return response

    async def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        return (await self._request(method, path, **kwargs)).json()

    async def _generate(
        self, path: str, body: dict, *, wait: bool, timeout: float, on_progress: ProgressCallback | None
    ) -> "Asset | JobInfo":
        body = {key: value for key, value in body.items() if value is not None}
        job = JobInfo.model_validate(await self._json("POST", path, json=body))
        if not wait:
            return job
        job = await self.wait_for_job(job, timeout=timeout, on_progress=on_progress)
        asset = await self.get_asset(job.result_asset_id)  # type: ignore[arg-type]
        asset.job = job
        return asset

    # -------------------------------- system ------------------------------- #

    async def health(self) -> dict:
        return await self._json("GET", "/api/health")

    async def providers(self) -> list[ProviderState]:
        """What serves each capability right now. Never includes API keys."""
        return [ProviderState.model_validate(item) for item in await self._json("GET", "/api/system/providers")]

    async def check_provider(self, kind: str) -> dict:
        """Live connectivity check: ``{"ok": bool, "detail": str, "models": [...]}``."""
        return await self._json("POST", f"/api/system/providers/{kind}/check")

    # ------------------------------- projects ------------------------------ #

    async def create_project(self, name: str, description: str = "") -> Project:
        return Project.model_validate(await self._json("POST", "/api/projects", json={"name": name, "description": description}))

    async def list_projects(self) -> list[Project]:
        return [Project.model_validate(item) for item in await self._json("GET", "/api/projects")]

    # --------------------------------- jobs -------------------------------- #

    async def get_job(self, job: JobInfo | str) -> JobInfo:
        return JobInfo.model_validate(await self._json("GET", f"/api/jobs/{_id(job)}"))

    async def cancel_job(self, job: JobInfo | str) -> JobInfo:
        return JobInfo.model_validate(await self._json("POST", f"/api/jobs/{_id(job)}/cancel"))

    async def retry_job(self, job: JobInfo | str) -> JobInfo:
        return JobInfo.model_validate(await self._json("POST", f"/api/jobs/{_id(job)}/retry"))

    async def wait_for_job(
        self, job: JobInfo | str, *, timeout: float = 600.0, on_progress: ProgressCallback | None = None
    ) -> JobInfo:
        """Poll until the job finishes. Raises :class:`JobFailedError` if it
        failed or was cancelled and :class:`JobTimeoutError` if time runs out."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            current = await self.get_job(job)
            if on_progress:
                on_progress(current)
            if current.status == "completed":
                return current
            if current.finished:
                raise JobFailedError(current)
            if loop.time() >= deadline:
                raise JobTimeoutError(current, timeout)
            await asyncio.sleep(self._poll_interval)

    # -------------------------------- assets ------------------------------- #

    async def get_asset(self, asset: Asset | str) -> Asset:
        return Asset.model_validate(await self._json("GET", f"/api/assets/{_id(asset)}"))

    async def list_assets(self, *, kind: str | None = None, project: Project | str | None = None, limit: int = 50) -> list[Asset]:
        params = {key: value for key, value in {"kind": kind, "project_id": _id(project), "limit": limit}.items() if value is not None}
        return [Asset.model_validate(item) for item in await self._json("GET", "/api/assets", params=params)]

    async def delete_asset(self, asset: Asset | str) -> None:
        await self._request("DELETE", f"/api/assets/{_id(asset)}")

    async def download(self, asset: Asset | str, path: str | Path) -> Path:
        """Save the asset's media file (MP3, MP4, PNG) to ``path``."""
        target = Path(path)
        response = await self._request("GET", f"/api/assets/{_id(asset)}/file", params={"download": 1})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return target

    async def upload_audio(
        self, path: str | Path, *, kind: str = "beat", title: str | None = None,
        bpm: float | None = None, project: Project | str | None = None,
    ) -> Asset:
        """Upload your own beat, vocal or song (``kind``: beat, vocals, song)."""
        source = Path(path)
        data = {key: str(value) for key, value in {"kind": kind, "title": title, "bpm": bpm, "project_id": _id(project)}.items() if value is not None}
        with source.open("rb") as handle:
            payload = await self._json("POST", "/api/assets/upload", files={"file": (source.name, handle)}, data=data)
        return Asset.model_validate(payload)

    # ------------------------------ generation ----------------------------- #

    async def generate_lyrics(
        self, prompt: str, *, project: Project | str | None = None, wait: bool = True,
        timeout: float = 600.0, on_progress: ProgressCallback | None = None, **options: Any,
    ) -> "Asset | JobInfo":
        """``options`` are lyric settings: genre, mood, language, style,
        troll_intensity, explicit, length, verses, chorus_style, persona..."""
        body = {"project_id": _id(project), "request": {"prompt": prompt, **options}}
        return await self._generate("/api/lyrics/generate", body, wait=wait, timeout=timeout, on_progress=on_progress)

    async def import_lyrics(self, title: str, text: str, *, project: Project | str | None = None) -> Asset:
        """Store lyrics you wrote yourself. ``[Verse 1]``-style headers mark sections."""
        payload = await self._json("POST", "/api/lyrics/import", json={"title": title, "text": text, "project_id": _id(project)})
        return Asset.model_validate(payload)

    async def generate_battle(
        self, topic: str, character_a: BattleCharacter | dict | str, character_b: BattleCharacter | dict | str, *,
        project: Project | str | None = None, wait: bool = True, timeout: float = 600.0,
        on_progress: ProgressCallback | None = None, **options: Any,
    ) -> "Asset | JobInfo":
        """A rap battle between two fictional characters, returned as lyrics."""
        def character(value: BattleCharacter | dict | str) -> dict:
            if isinstance(value, str):
                return {"name": value}
            return value.model_dump() if isinstance(value, BattleCharacter) else value

        request = {"topic": topic, "character_a": character(character_a), "character_b": character(character_b), **options}
        body = {"project_id": _id(project), "request": request}
        return await self._generate("/api/battles/generate", body, wait=wait, timeout=timeout, on_progress=on_progress)

    async def generate_beat(
        self, *, project: Project | str | None = None, lyrics: Asset | str | None = None, wait: bool = True,
        timeout: float = 900.0, on_progress: ProgressCallback | None = None, **options: Any,
    ) -> "Asset | JobInfo":
        """``options``: genre, bpm, mood, instruments, energy, duration_seconds,
        key, description, variations. With several variations the first is
        returned; ``asset.job.result_asset_ids`` lists them all."""
        body = {"project_id": _id(project), "lyrics_asset_id": _id(lyrics), "request": options}
        return await self._generate("/api/beats/generate", body, wait=wait, timeout=timeout, on_progress=on_progress)

    async def generate_vocals(
        self, lyrics: Asset | str, *, beat: Asset | str | None = None, bpm: float | None = None,
        voice: str | None = None, voice_b: str | None = None, voice_profile: VoiceProfile | str | None = None,
        project: Project | str | None = None, wait: bool = True, timeout: float = 900.0,
        on_progress: ProgressCallback | None = None,
    ) -> "Asset | JobInfo":
        """Perform lyrics as a vocal track in time with a tempo. Check
        ``asset.meta["delivery"]``: speech providers give ``"spoken"``."""
        body = {
            "project_id": _id(project), "lyrics_asset_id": _id(lyrics), "beat_asset_id": _id(beat), "bpm": bpm,
            "voice": voice, "voice_b": voice_b, "voice_profile_id": _id(voice_profile),
        }
        return await self._generate("/api/vocals/generate", body, wait=wait, timeout=timeout, on_progress=on_progress)

    async def generate_song(
        self, lyrics: Asset | str, beat: Asset | str | None = None, *, vocals: Asset | str | None = None,
        mode: str = "mix", title: str | None = None, voice: str | None = None, voice_b: str | None = None,
        voice_profile: VoiceProfile | str | None = None, project: Project | str | None = None,
        wait: bool = True, timeout: float = 1800.0, on_progress: ProgressCallback | None = None, **options: Any,
    ) -> "Asset | JobInfo":
        """Mix vocals over a beat (``mode="mix"``; vocals are generated if not
        given), or ask a singing music model for the whole song (``mode="model"``).
        ``options``: vocal_gain_db, beat_gain_db, style_prompt, duration_seconds."""
        body = {
            "project_id": _id(project), "mode": mode, "lyrics_asset_id": _id(lyrics), "beat_asset_id": _id(beat),
            "vocals_asset_id": _id(vocals), "title": title, "voice": voice, "voice_b": voice_b,
            "voice_profile_id": _id(voice_profile), **options,
        }
        return await self._generate("/api/songs/generate", body, wait=wait, timeout=timeout, on_progress=on_progress)

    async def generate_music_video(
        self, audio: Asset | str | None = None, *, lyrics: Asset | str | None = None, style: str = "lyric video",
        aspect: str = "16:9", subtitles: bool = True, project: Project | str | None = None, wait: bool = True,
        timeout: float = 3600.0, on_progress: ProgressCallback | None = None, **options: Any,
    ) -> "Asset | JobInfo":
        """Render an MP4 for a song (or from lyrics alone). ``options``: title,
        duration_seconds (without audio), notes."""
        body = {
            "project_id": _id(project), "audio_asset_id": _id(audio), "lyrics_asset_id": _id(lyrics),
            "style": style, "aspect": aspect, "subtitles": subtitles, **options,
        }
        return await self._generate("/api/videos/generate", body, wait=wait, timeout=timeout, on_progress=on_progress)

    async def generate_artwork(
        self, title: str, *, lyrics: Asset | str | None = None, project: Project | str | None = None,
        wait: bool = True, timeout: float = 900.0, on_progress: ProgressCallback | None = None, **options: Any,
    ) -> "Asset | JobInfo":
        """A 1024x1024 cover. ``options``: genre, mood, style, character, notes."""
        body = {"project_id": _id(project), "lyrics_asset_id": _id(lyrics), "title": title, **options}
        return await self._generate("/api/artwork/generate", body, wait=wait, timeout=timeout, on_progress=on_progress)

    async def troll(
        self, situation: str, *, kind: str = "diss_track", style: str = "trap", intensity: str = "savage",
        project: Project | str | None = None, with_video: bool = False, with_cover: bool = True,
        wait: bool = True, timeout: float = 3600.0, on_progress: ProgressCallback | None = None, **options: Any,
    ) -> "Asset | JobInfo":
        """The one-button meme: words, vocals, beat, mix, fake album cover and,
        for ``kind="meme_video"`` (or ``with_video=True``), a vertical MP4.

        Returns the video if one was made, otherwise the song (or the beat for
        ``funny_beat``). ``asset.job.result_asset_ids`` lists every file made.
        ``options``: target, names, rapper_name, delivery, explicit, language.
        """
        request = {"situation": situation, "kind": kind, "style": style, "intensity": intensity, **options}
        body = {"project_id": _id(project), "request": request, "with_video": with_video, "with_cover": with_cover}
        return await self._generate("/api/troll", body, wait=wait, timeout=timeout, on_progress=on_progress)

    async def random_troll(self) -> dict:
        """A random situation and settings, ready to pass to :meth:`troll`."""
        return await self._json("GET", "/api/troll/random")

    # ----------------------------- voice profiles -------------------------- #

    async def create_voice_profile(
        self, name: str, sample_path: str | Path, *, owner_name: str, consent_statement: str, consent_confirmed: bool,
    ) -> VoiceProfile:
        """Register an authorized voice. The backend refuses this unless the
        voice's owner has explicitly consented (``consent_confirmed=True``)."""
        source = Path(sample_path)
        data = {
            "name": name, "owner_name": owner_name, "consent_statement": consent_statement,
            "consent_confirmed": "true" if consent_confirmed else "false",
        }
        with source.open("rb") as handle:
            payload = await self._json("POST", "/api/voices", files={"file": (source.name, handle)}, data=data)
        return VoiceProfile.model_validate(payload)

    async def list_voice_profiles(self) -> list[VoiceProfile]:
        return [VoiceProfile.model_validate(item) for item in await self._json("GET", "/api/voices")]

    async def delete_voice_profile(self, profile: VoiceProfile | str) -> None:
        await self._request("DELETE", f"/api/voices/{_id(profile)}")

    async def stock_voices(self) -> dict:
        """Voices the active provider offers, and whether it can sing or clone."""
        return await self._json("GET", "/api/voices/stock")


# ------------------------------ sync client -------------------------------- #


class TrollMusicClient:
    """Blocking client with the same methods as :class:`AsyncTrollMusicClient`.

    Not for use inside a running event loop; use the async client there.
    """

    def __init__(self, api_key: str | None = None, **kwargs: Any) -> None:
        self._runner = asyncio.Runner()
        self._async = self._runner.run(self._build(api_key, kwargs))
        self.base_url = self._async.base_url

    @staticmethod
    async def _build(api_key: str | None, kwargs: dict) -> AsyncTrollMusicClient:
        return AsyncTrollMusicClient(api_key, **kwargs)

    def close(self) -> None:
        self._runner.run(self._async.aclose())
        self._runner.close()

    def __enter__(self) -> "TrollMusicClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _blocking(name: str) -> Callable[..., Any]:
    method = getattr(AsyncTrollMusicClient, name)

    @functools.wraps(method)
    def call(self: TrollMusicClient, *args: Any, **kwargs: Any) -> Any:
        return self._runner.run(method(self._async, *args, **kwargs))

    return call


for _name, _member in inspect.getmembers(AsyncTrollMusicClient, inspect.iscoroutinefunction):
    if not _name.startswith("_") and _name != "aclose":
        setattr(TrollMusicClient, _name, _blocking(_name))
