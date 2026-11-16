"""High-level entry points: :class:`TrollMusic` (sync) and :class:`AsyncTrollMusic`."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .config import LLMConfig, build_text_provider
from .errors import FeatureNotAvailableError, ProviderNotConfiguredError
from .lyrics.service import LyricsService
from .providers.base import ProviderStatus, TextGenerationProvider
from .types import Lyrics, LyricsRequest, RewriteMode

_NO_TEXT_PROVIDER = (
    "No text provider is configured. Set TROLL_LLM_PROVIDER (for example 'ollama'), "
    "or pass llm=LLMConfig(...) or text_provider=... to TrollMusic()."
)


_NEEDS_BACKEND = (
    "{} are assembled by the backend (FFmpeg mixing and rendering). Start the backend and use "
    "TrollMusic(base_url='http://localhost:8000') instead."
)


class AsyncTrollMusic:
    """Async studio. Each generation module is independent; use only what you need."""

    def __init__(
        self,
        *,
        llm: LLMConfig | None = None,
        text_provider: TextGenerationProvider | None = None,
    ) -> None:
        self._llm = llm or LLMConfig.from_env()
        self._text_provider = text_provider or build_text_provider(self._llm)

    @property
    def text_provider(self) -> TextGenerationProvider | None:
        return self._text_provider

    def _lyrics_service(self) -> LyricsService:
        if self._text_provider is None:
            raise ProviderNotConfiguredError(_NO_TEXT_PROVIDER)
        return LyricsService(self._text_provider, json_mode=self._llm.json_mode)

    async def check_text_provider(self) -> ProviderStatus:
        if self._text_provider is None:
            return ProviderStatus(ok=False, detail=_NO_TEXT_PROVIDER)
        return await self._text_provider.check()

    # ------------------------------ lyrics -------------------------------- #

    async def generate_lyrics(
        self,
        prompt: str | None = None,
        *,
        request: LyricsRequest | None = None,
        **options: Any,
    ) -> Lyrics:
        """Generate lyrics from a prompt plus options, or from a full request.

        ``options`` are :class:`LyricsRequest` fields, e.g. ``genre="drill"``.
        """
        if request is None:
            if prompt is None:
                raise ValueError("Pass a prompt or a LyricsRequest.")
            request = LyricsRequest(prompt=prompt, **options)
        return await self._lyrics_service().generate(request)

    async def regenerate_section(
        self,
        lyrics: Lyrics,
        section_id: str,
        *,
        request: LyricsRequest | None = None,
        instruction: str | None = None,
    ) -> Lyrics:
        return await self._lyrics_service().regenerate_section(
            lyrics, section_id, request=request, instruction=instruction
        )

    async def rewrite_lyrics(
        self,
        lyrics: Lyrics,
        mode: RewriteMode | str = RewriteMode.FUNNIER,
        *,
        request: LyricsRequest | None = None,
        instruction: str | None = None,
        rhyme_scheme: str | None = None,
    ) -> Lyrics:
        return await self._lyrics_service().rewrite(
            lyrics,
            RewriteMode(mode),
            request=request,
            instruction=instruction,
            rhyme_scheme=rhyme_scheme,
        )

    # ------------------------------- beats -------------------------------- #

    async def generate_beat(self, out_path: str | Path = "beat.wav", *, seed: int = 0, **options: Any) -> Path:
        """Generate an instrumental and write it to ``out_path``.

        ``options`` are :class:`BeatRequest` fields (genre, bpm, mood, energy,
        duration_seconds...). Uses ``TROLL_MUSIC_PROVIDER``; the default is the
        built-in beat engine, which is a synthesizer, not an AI model. The
        returned path may differ from ``out_path`` in extension.
        """
        from .providers import registry
        from .providers.base import ProviderKind
        from .types import BeatRequest

        provider = registry.build(ProviderKind.MUSIC, registry.ProviderConfig.from_env(ProviderKind.MUSIC, "procedural"))
        if provider is None:
            raise ProviderNotConfiguredError("TROLL_MUSIC_PROVIDER is set to 'none'.")
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        return await provider.generate_instrumental(BeatRequest(**options), target, seed)  # type: ignore[attr-defined]

    # ------------------- needs the backend's media pipeline ---------------- #

    async def generate_vocals(self, **_options: Any):
        raise FeatureNotAvailableError(_NEEDS_BACKEND.format("Vocal tracks"))

    async def generate_song(self, **_options: Any):
        raise FeatureNotAvailableError(_NEEDS_BACKEND.format("Songs"))

    async def generate_music_video(self, **_options: Any):
        raise FeatureNotAvailableError(_NEEDS_BACKEND.format("Music videos"))


class TrollMusic:
    """Two ways to use the studio from Python.

    ``TrollMusic(api_key=..., base_url=...)`` returns a
    :class:`~troll_music_ai.client.TrollMusicClient` that talks to a running
    backend: lyrics, beats, vocals, songs, videos, artwork, voice profiles.

    ``TrollMusic()`` with neither argument is the in-process toolkit: lyrics
    (with your LLM) and beats, with no server. Inside a running event loop use
    :class:`AsyncTrollMusic` or :class:`~troll_music_ai.client.AsyncTrollMusicClient`.
    """

    def __new__(cls, *, api_key: str | None = None, base_url: str | None = None, **kwargs: Any):
        if api_key is not None or base_url is not None:
            from .client import TrollMusicClient

            return TrollMusicClient(api_key, base_url=base_url, **kwargs)
        return super().__new__(cls)

    def __init__(self, **kwargs: Any) -> None:
        self._async = AsyncTrollMusic(**kwargs)

    @property
    def text_provider(self) -> TextGenerationProvider | None:
        return self._async.text_provider

    def check_text_provider(self) -> ProviderStatus:
        return asyncio.run(self._async.check_text_provider())

    def generate_lyrics(self, prompt: str | None = None, **kwargs: Any) -> Lyrics:
        return asyncio.run(self._async.generate_lyrics(prompt, **kwargs))

    def regenerate_section(self, lyrics: Lyrics, section_id: str, **kwargs: Any) -> Lyrics:
        return asyncio.run(self._async.regenerate_section(lyrics, section_id, **kwargs))

    def rewrite_lyrics(self, lyrics: Lyrics, mode: RewriteMode | str = "funnier", **kwargs: Any) -> Lyrics:
        return asyncio.run(self._async.rewrite_lyrics(lyrics, mode, **kwargs))

    def generate_beat(self, out_path: str | Path = "beat.wav", **kwargs: Any) -> Path:
        return asyncio.run(self._async.generate_beat(out_path, **kwargs))

    def generate_song(self, **kwargs: Any):
        return asyncio.run(self._async.generate_song(**kwargs))

    def generate_vocals(self, **kwargs: Any):
        return asyncio.run(self._async.generate_vocals(**kwargs))

    def generate_music_video(self, **kwargs: Any):
        return asyncio.run(self._async.generate_music_video(**kwargs))
