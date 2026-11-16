"""Resolves which provider serves each capability.

Order of precedence: a test override, then Model Settings (the
``provider_settings`` table), then the environment. Built providers are cached
until their settings change.
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import Settings
from backend.models.tables import ProviderSetting
from troll_music_ai import ProviderNotConfiguredError, TrollMusicError
from troll_music_ai.providers import Provider, ProviderConfig, ProviderKind, registry

log = logging.getLogger(__name__)

KINDS = ("text", "music", "voice", "image")
LABELS = {
    "text": "Lyrics and text",
    "music": "Beats and music",
    "voice": "Vocals and voice",
    "image": "Artwork and video scenes",
}
_UNSET = object()


class ProviderManager:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        overrides: dict[str, Provider | None] | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._overrides = dict(overrides or {})
        self._cache: dict[str, tuple[Provider | None, str]] = {}
        self._lock = threading.Lock()

    def source(self, kind: str) -> str:
        if kind in self._overrides:
            return "override"
        with self._session_factory() as session:
            return "settings" if session.get(ProviderSetting, kind) else "environment"

    def config(self, kind: str) -> ProviderConfig:
        """Effective configuration, with registry defaults filled in."""
        with self._session_factory() as session:
            row = session.get(ProviderSetting, kind)
            if row is None:
                config = self._settings.provider_config(kind)
            else:
                env = self._settings.provider_config(kind)
                config = ProviderConfig(
                    provider=row.provider if row.enabled else "none",
                    model=row.model,
                    base_url=row.base_url,
                    # A key saved in settings wins; otherwise reuse the environment's
                    # key when the provider is the same one.
                    api_key=row.api_key or (env.api_key if env.provider == row.provider else None),
                    options=env.options,
                )
        return registry.resolve(ProviderKind(kind), config)

    def _resolve(self, kind: str) -> tuple[Provider | None, str]:
        if kind in self._overrides:
            return self._overrides[kind], ""
        with self._lock:
            if kind not in self._cache:
                try:
                    self._cache[kind] = (registry.build(ProviderKind(kind), self.config(kind)), "")
                except TrollMusicError as exc:
                    # A bad provider config must not take the studio down.
                    log.warning("%s provider disabled: %s", kind, exc.message)
                    self._cache[kind] = (None, exc.message)
            return self._cache[kind]

    def get(self, kind: str) -> Provider | None:
        return self._resolve(kind)[0]

    def error(self, kind: str) -> str:
        return self._resolve(kind)[1]

    def require(self, kind: str) -> Provider:
        provider, error = self._resolve(kind)
        if provider is None:
            raise ProviderNotConfiguredError(
                error
                or f"No {LABELS[kind].lower()} provider is configured. Choose one in Model Settings."
            )
        return provider

    def invalidate(self, kind: str) -> None:
        with self._lock:
            self._cache.pop(kind, None)

    def json_mode(self) -> bool:
        return bool(self._settings.llm_json_mode)
