"""Provider interfaces.

One abstract class per capability. The application only talks to these
interfaces, so swapping one model for another means writing one adapter and
registering it (see ``registry.py``).

Providers write their output to a path chosen by the caller. Post-processing
(normalization, format conversion, mixing) is the caller's job, not the
provider's.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..types import BeatRequest, ImageRequest, SongRequest, SpeechLine


class ProviderKind(StrEnum):
    TEXT = "text"
    MUSIC = "music"
    VOICE = "voice"
    IMAGE = "image"
    VIDEO = "video"


class ProviderInfo(BaseModel):
    name: str
    kind: ProviderKind
    model: str | None = None
    is_mock: bool = False
    # False for built-in engines (procedural synth, system speech, typography):
    # real output, but not produced by an AI model. Shown to users.
    is_ai: bool = True
    endpoint: str | None = None  # never includes credentials


class ProviderStatus(BaseModel):
    ok: bool
    detail: str
    models: list[str] = Field(default_factory=list)


class Provider(ABC):
    @property
    @abstractmethod
    def info(self) -> ProviderInfo: ...

    @abstractmethod
    async def check(self) -> ProviderStatus:
        """Cheap health probe. Must not raise."""


# ------------------------------- text ------------------------------------- #


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class TextRequest(BaseModel):
    messages: list[ChatMessage]
    temperature: float | None = 0.9
    max_tokens: int = 2500
    json_mode: bool = False


class TextResult(BaseModel):
    text: str
    model: str | None = None


class TextGenerationProvider(Provider):
    @abstractmethod
    async def generate_text(self, request: TextRequest) -> TextResult: ...


# ------------------------------- music ------------------------------------ #


class MusicCapabilities(BaseModel):
    exact_bpm: bool = False  # tempo is guaranteed, not just prompted
    exact_duration: bool = False
    max_duration_seconds: float | None = None  # longer requests are looped by the caller
    with_vocals: bool = False  # can sing supplied lyrics (full-song generation)
    key_control: bool = False


class MusicGenerationProvider(Provider):
    @property
    @abstractmethod
    def capabilities(self) -> MusicCapabilities: ...

    @abstractmethod
    async def generate_instrumental(self, request: BeatRequest, out_path: Path, seed: int) -> Path:
        """Write one instrumental (no vocals) and return the file written.

        The returned path may differ from ``out_path`` in extension only.
        """

    async def generate_song(self, request: SongRequest, out_path: Path, seed: int) -> Path:
        """Full song with sung vocals. Only when ``capabilities.with_vocals``."""
        raise NotImplementedError


# ------------------------------- voice ------------------------------------ #


class VoiceCapabilities(BaseModel):
    speech: bool = True
    singing: bool = False  # sings in time and in key. Speech models do not.
    cloning: bool = False  # can speak with an authorized, user-supplied voice
    conversion: bool = False  # can re-voice an existing vocal recording


class VoiceProvider(Provider):
    """Speech synthesis, with optional cloning and voice conversion.

    Singing is deliberately not assumed: ``capabilities.singing`` is False for
    every text-to-speech model.
    """

    @property
    @abstractmethod
    def capabilities(self) -> VoiceCapabilities: ...

    @abstractmethod
    async def voices(self) -> list[str]:
        """Names of the stock voices that can be used without a profile."""

    @abstractmethod
    async def synthesize_lines(self, lines: list[SpeechLine], out_dir: Path) -> list[Path]:
        """Speak each line into its own audio file, in order."""

    async def create_voice(self, name: str, sample_path: Path) -> str:
        """Register a cloned voice; return the provider's id for it.

        Callers must have recorded the voice owner's consent first.
        """
        raise NotImplementedError

    async def delete_voice(self, provider_voice_id: str) -> None:
        raise NotImplementedError

    async def convert_voice(self, source_path: Path, provider_voice_id: str, out_path: Path) -> Path:
        """Re-voice ``source_path`` (speech or singing) with a cloned voice."""
        raise NotImplementedError


# --------------------------- image and video ------------------------------ #


class ImageGenerationProvider(Provider):
    @abstractmethod
    async def generate_image(self, request: ImageRequest, out_path: Path) -> Path: ...


class VideoGenerationProvider(Provider):
    """Optional image-to-video animation. No adapter exists yet; the video
    pipeline renders stills with FFmpeg when none is configured."""

    @abstractmethod
    async def animate(self, image_path: Path, prompt: str, seconds: float, out_path: Path) -> Path: ...
