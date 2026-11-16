"""TROLL-MUSIC-AI: roast it, rap it, release it."""

from .client import (
    ApiError,
    Asset,
    AsyncTrollMusicClient,
    AuthenticationError,
    JobFailedError,
    JobInfo,
    JobTimeoutError,
    TrollMusicClient,
)
from .config import LLMConfig, build_text_provider
from .errors import (
    FeatureNotAvailableError,
    LyricsParseError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderUnavailableError,
    TrollMusicError,
)
from .studio import AsyncTrollMusic, TrollMusic
from .types import (
    BattleCharacter,
    BattleRequest,
    BeatRequest,
    ChorusStyle,
    GenerationMeta,
    Lyrics,
    LyricSection,
    LyricsRequest,
    LyricStyle,
    RewriteMode,
    RhymeComplexity,
    SectionType,
    SongLength,
)

__version__ = "0.2.0"

__all__ = [
    "ApiError",
    "Asset",
    "AsyncTrollMusic",
    "AsyncTrollMusicClient",
    "AuthenticationError",
    "BattleCharacter",
    "BattleRequest",
    "BeatRequest",
    "JobFailedError",
    "JobInfo",
    "JobTimeoutError",
    "TrollMusicClient",
    "ChorusStyle",
    "FeatureNotAvailableError",
    "GenerationMeta",
    "LLMConfig",
    "LyricSection",
    "LyricStyle",
    "Lyrics",
    "LyricsParseError",
    "LyricsRequest",
    "ProviderNotConfiguredError",
    "ProviderResponseError",
    "ProviderUnavailableError",
    "RewriteMode",
    "RhymeComplexity",
    "SectionType",
    "SongLength",
    "TrollMusic",
    "TrollMusicError",
    "build_text_provider",
]
