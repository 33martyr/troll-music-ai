"""Backend settings, read from the environment or a ``.env`` file."""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from troll_music_ai import LLMConfig
from troll_music_ai.providers import ProviderConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TROLL_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # SQLite keeps local setup dependency-free. Use PostgreSQL in deployment:
    # postgresql+psycopg://user:pass@host:5432/troll
    database_url: str = "sqlite:///./data/troll.db"
    storage_dir: str = "./data/storage"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    job_workers: int = 2
    max_upload_mb: int = 50
    ffmpeg_path: str | None = None  # defaults to PATH, then the imageio-ffmpeg binary
    # When set, every API call needs "Authorization: Bearer <key>".
    api_key: SecretStr | None = None

    # Built-in engines are the defaults, so the studio works with no setup.
    music_provider: str = "procedural"
    music_model: str | None = None
    music_base_url: str | None = None
    music_api_key: SecretStr | None = None
    voice_provider: str = "system_tts"
    voice_model: str | None = None
    voice_base_url: str | None = None
    voice_api_key: SecretStr | None = None
    image_provider: str = "typographic"
    image_model: str | None = None
    image_base_url: str | None = None
    image_api_key: SecretStr | None = None

    llm_provider: str = "none"
    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None  # SecretStr keeps the key out of logs and reprs
    llm_model: str | None = None
    llm_timeout: float = 120.0
    llm_json_mode: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def provider_config(self, kind: str) -> ProviderConfig:
        """Provider settings from the environment for one kind."""
        prefix = "llm" if kind == "text" else kind
        if not hasattr(self, f"{prefix}_provider"):
            return ProviderConfig()
        key = getattr(self, f"{prefix}_api_key")
        options = {"timeout": self.llm_timeout, "json_mode": self.llm_json_mode} if kind == "text" else {}
        return ProviderConfig(
            provider=getattr(self, f"{prefix}_provider").strip().lower(),
            model=getattr(self, f"{prefix}_model") or None,
            base_url=getattr(self, f"{prefix}_base_url") or None,
            api_key=key.get_secret_value() if key else None,
            options=options,
        )

    def llm_config(self) -> LLMConfig:
        return LLMConfig(
            provider=self.llm_provider.strip().lower(),
            base_url=self.llm_base_url or None,
            api_key=self.llm_api_key.get_secret_value() if self.llm_api_key else None,
            model=self.llm_model or None,
            timeout=self.llm_timeout,
            json_mode=self.llm_json_mode,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
