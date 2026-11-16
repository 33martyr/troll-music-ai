"""Exception hierarchy for the toolkit.

Every error a caller is expected to handle derives from :class:`TrollMusicError`
and carries a stable ``code`` so API layers can map it without string matching.
"""

from __future__ import annotations


class TrollMusicError(Exception):
    code = "troll_music_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ProviderNotConfiguredError(TrollMusicError):
    """No provider is configured for the requested capability."""

    code = "provider_not_configured"


class ProviderUnavailableError(TrollMusicError):
    """The provider is configured but could not be reached (network, timeout)."""

    code = "provider_unavailable"


class ProviderResponseError(TrollMusicError):
    """The provider answered with an error or an unusable payload."""

    code = "provider_response_error"

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LyricsParseError(TrollMusicError):
    """The model's output could not be turned into structured lyrics."""

    code = "lyrics_parse_error"


class FeatureNotAvailableError(TrollMusicError):
    """The capability is defined in the architecture but has no adapter yet."""

    code = "feature_not_available"
