"""Text-provider configuration helpers.

``LLMConfig`` is the convenient form for scripts; the general mechanism for
every provider kind is :mod:`troll_music_ai.providers.registry`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .providers import registry
from .providers.base import ProviderKind, TextGenerationProvider

LLM_PROVIDER_NAMES = ("none", *(spec.name for spec in registry.specs(ProviderKind.TEXT)))


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "none"
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: float = 120.0
    json_mode: bool = False

    @classmethod
    def from_env(cls) -> "LLMConfig":
        env = os.environ
        return cls(
            provider=(env.get("TROLL_LLM_PROVIDER") or "none").strip().lower(),
            base_url=env.get("TROLL_LLM_BASE_URL") or None,
            api_key=env.get("TROLL_LLM_API_KEY") or None,
            model=env.get("TROLL_LLM_MODEL") or None,
            timeout=float(env.get("TROLL_LLM_TIMEOUT") or 120),
            json_mode=(env.get("TROLL_LLM_JSON_MODE") or "").lower() in ("1", "true", "yes"),
        )

    def provider_config(self) -> registry.ProviderConfig:
        return registry.ProviderConfig(
            provider=self.provider, model=self.model, base_url=self.base_url, api_key=self.api_key,
            options={"timeout": self.timeout, "json_mode": self.json_mode},
        )


def build_text_provider(config: LLMConfig) -> TextGenerationProvider | None:
    """Return the configured text provider, or ``None`` when none is selected."""
    return registry.build(ProviderKind.TEXT, config.provider_config())  # type: ignore[return-value]
