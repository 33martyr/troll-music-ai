"""The provider registry: what can be configured, what it needs, how to build it.

Each :class:`ProviderSpec` describes one provider honestly: where it runs,
what hardware and credentials it needs, its licence and which generation
parameters it honours. Nothing here contacts a provider; use ``check()`` on
a built provider for live status.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from ..errors import ProviderNotConfiguredError
from .base import Provider, ProviderKind

ENV_PREFIX = {
    ProviderKind.TEXT: "TROLL_LLM",
    ProviderKind.MUSIC: "TROLL_MUSIC",
    ProviderKind.VOICE: "TROLL_VOICE",
    ProviderKind.IMAGE: "TROLL_IMAGE",
    ProviderKind.VIDEO: "TROLL_VIDEO",
}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "none"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    options: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, kind: ProviderKind, default: str = "none") -> "ProviderConfig":
        prefix = ENV_PREFIX[kind]
        env = os.environ
        return cls(
            provider=(env.get(f"{prefix}_PROVIDER") or default).strip().lower(),
            model=env.get(f"{prefix}_MODEL") or None,
            base_url=env.get(f"{prefix}_BASE_URL") or None,
            api_key=env.get(f"{prefix}_API_KEY") or None,
        )


@dataclass(frozen=True)
class ProviderSpec:
    kind: ProviderKind
    name: str
    label: str
    description: str
    factory: Callable[[ProviderConfig], Provider]
    local: bool = True  # runs on this machine (or a server you run) vs a hosted service
    is_ai: bool = True  # False for built-in engines
    is_mock: bool = False
    needs_api_key: bool = False
    needs_base_url: bool = False
    needs_model: bool = False
    default_base_url: str | None = None
    default_model: str | None = None
    suggested_models: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    params: tuple[str, ...] = ()  # generation parameters the provider honours
    hardware: str = "None"
    license: str = ""
    commercial_use: bool | None = None  # None = depends, read the licence
    packages: tuple[str, ...] = ()  # importable modules it needs
    setup: str = ""
    verified: bool = True  # False = adapter written but not yet run against the real thing

    def missing_packages(self) -> list[str]:
        return [name for name in self.packages if importlib.util.find_spec(name) is None]


_REGISTRY: dict[tuple[ProviderKind, str], ProviderSpec] = {}


def register(spec: ProviderSpec) -> ProviderSpec:
    _REGISTRY[(spec.kind, spec.name)] = spec
    return spec


def get_spec(kind: ProviderKind, name: str) -> ProviderSpec | None:
    return _REGISTRY.get((ProviderKind(kind), name))


def specs(kind: ProviderKind | None = None) -> list[ProviderSpec]:
    return [spec for (spec_kind, _), spec in _REGISTRY.items() if kind is None or spec_kind == kind]


def resolve(kind: ProviderKind, config: ProviderConfig) -> ProviderConfig:
    """Fill in the spec's defaults for anything the config leaves unset."""
    spec = get_spec(kind, config.provider)
    if spec is None:
        return config
    return ProviderConfig(
        provider=config.provider,
        model=config.model or spec.default_model,
        base_url=config.base_url or spec.default_base_url,
        api_key=config.api_key,
        options=config.options,
    )


def build(kind: ProviderKind, config: ProviderConfig) -> Provider | None:
    """Build the configured provider, or ``None`` when none is selected.

    Raises :class:`ProviderNotConfiguredError` when a provider is selected but
    cannot work as configured, so misconfiguration is loud, not silent.
    """
    kind = ProviderKind(kind)
    name = (config.provider or "none").strip().lower()
    if name in ("", "none"):
        return None
    prefix = ENV_PREFIX[kind]
    spec = get_spec(kind, name)
    if spec is None:
        choices = ", ".join(["none", *(s.name for s in specs(kind))])
        raise ProviderNotConfiguredError(f"Unknown {prefix}_PROVIDER '{name}'. Choose one of: {choices}")
    config = resolve(kind, config)
    if spec.needs_base_url and not config.base_url:
        raise ProviderNotConfiguredError(f"{prefix}_BASE_URL is required for '{name}'.")
    if spec.needs_model and not config.model:
        raise ProviderNotConfiguredError(f"{prefix}_MODEL is required for '{name}'.")
    if spec.needs_api_key and not config.api_key:
        raise ProviderNotConfiguredError(f"{prefix}_API_KEY is required for '{name}'.")
    missing = spec.missing_packages()
    if missing:
        raise ProviderNotConfiguredError(
            f"'{name}' needs Python package(s) that are not installed: {', '.join(missing)}. {spec.setup}".strip()
        )
    return spec.factory(config)


# --------------------------------------------------------------------------- #
# Registrations
# --------------------------------------------------------------------------- #


def _register_all() -> None:
    from .images import ComfyUIProvider, OpenAIImagesProvider, PollinationsImageProvider, TypographicProvider
    from .mock import MockTextProvider
    from .music_models import AceStepProvider, ElevenLabsMusicProvider, MusicGenProvider
    from .openai_compatible import OpenAICompatibleProvider
    from .procedural import ProceduralBeatProvider
    from .voice import ChatterboxProvider, ElevenLabsVoiceProvider, OpenAISpeechProvider, SystemSpeechProvider

    T, M, V, I = ProviderKind.TEXT, ProviderKind.MUSIC, ProviderKind.VOICE, ProviderKind.IMAGE
    lyric_params = ("genre", "mood", "language", "style", "troll_intensity", "explicit", "length", "verses", "chorus_style", "rhyme_complexity", "persona")

    def chat(name: str, **extra):
        def factory(c: ProviderConfig) -> Provider:
            return OpenAICompatibleProvider(
                base_url=c.base_url, model=c.model, api_key=c.api_key, name=name,
                timeout=float(c.options.get("timeout", 120)), **extra,
            )
        return factory

    register(ProviderSpec(
        T, "ollama", "Ollama", "Local LLMs through Ollama's OpenAI-compatible API.", chat("ollama"),
        default_base_url="http://localhost:11434/v1", default_model="llama3.2",
        suggested_models=("llama3.2", "qwen2.5:7b", "gemma3:4b", "mistral"), params=lyric_params,
        hardware="CPU works; a GPU with 4 GB+ VRAM is much faster", license="Ollama: MIT. Each model has its own licence.",
        setup="Install Ollama, then: ollama pull llama3.2",
    ))
    register(ProviderSpec(
        T, "openai_compatible", "OpenAI-compatible API", "LM Studio, vLLM, llama.cpp, OpenRouter, Groq and similar.",
        chat("openai_compatible"), local=False, needs_base_url=True, needs_model=True, params=lyric_params,
        license="Depends on the service and model.", setup="Set the base URL (ending in /v1), model and key.",
    ))
    register(ProviderSpec(
        T, "openai", "OpenAI", "OpenAI's hosted chat models.",
        chat("openai", max_tokens_param="max_completion_tokens", send_temperature=False),
        local=False, needs_api_key=True, needs_model=True, default_base_url="https://api.openai.com/v1",
        params=lyric_params, license="Commercial API terms.", commercial_use=True, verified=False,
    ))
    register(ProviderSpec(
        T, "pollinations", "Pollinations (free, hosted)", "Keyless hosted LLM. Rate-limited; prompts leave this machine.",
        chat("pollinations", extra_body={"reasoning_effort": "low"}, min_max_tokens=8000), local=False, default_base_url="https://text.pollinations.ai/openai", default_model="openai-fast",
        params=lyric_params, license="Pollinations terms of service.", setup="No key needed. Good for trying the studio.",
    ))
    register(ProviderSpec(
        T, "mock", "Mock (tests only)", "Placeholder text for UI development. Never real lyrics.",
        lambda c: MockTextProvider(), is_ai=False, is_mock=True,
    ))

    beat_params = ("genre", "mood", "instruments", "energy", "duration_seconds", "description", "variations")
    register(ProviderSpec(
        M, "procedural", "Built-in beat engine", "Drum machine and synth written in NumPy. Exact BPM and duration. Not an AI model.",
        lambda c: ProceduralBeatProvider(), is_ai=False, default_model="troll-synth-1",
        capabilities=("instrumental",), params=(*beat_params, "bpm", "key"), packages=("numpy",),
        license="MIT (part of this project). Output is yours.", commercial_use=True,
    ))
    register(ProviderSpec(
        M, "musicgen", "MusicGen (local)", "Meta's text-to-music model via transformers. Up to 30 s per pass; longer beats are looped.",
        lambda c: MusicGenProvider(model=c.model, allow_download=bool(c.options.get("allow_download"))),
        default_model="facebook/musicgen-small",
        suggested_models=("facebook/musicgen-small", "facebook/musicgen-medium", "facebook/musicgen-stereo-small"),
        capabilities=("instrumental",), params=beat_params, packages=("torch", "transformers"),
        hardware="GPU with 4 GB+ VRAM recommended (small). Runs on CPU, slowly.",
        license="Code MIT, weights CC-BY-NC 4.0: non-commercial use only.", commercial_use=False,
        setup="pip install torch transformers, then: python scripts/download_models.py musicgen",
    ))
    register(ProviderSpec(
        M, "acestep", "ACE-Step 1.5 (local server)", "Open music foundation model. Instrumentals and full songs with sung lyrics.",
        lambda c: AceStepProvider(base_url=c.base_url, api_key=c.api_key, model=c.model),
        default_base_url="http://localhost:8001", capabilities=("instrumental", "full_song_with_vocals"),
        params=(*beat_params, "bpm", "key"), hardware="CUDA GPU; about 5 GB of weights; Python 3.11-3.12 in its own environment",
        license="MIT (code). Check the model card before commercial release.", verified=False,
        setup="Clone ace-step/ACE-Step-1.5 and run: uv run acestep-api",
    ))
    register(ProviderSpec(
        M, "elevenlabs_music", "ElevenLabs Music (hosted)", "Hosted text-to-music. No GPU needed.",
        lambda c: ElevenLabsMusicProvider(base_url=c.base_url, api_key=c.api_key, model=c.model),
        local=False, needs_api_key=True, default_base_url="https://api.elevenlabs.io", default_model="music_v1",
        capabilities=("instrumental",), params=beat_params, license="ElevenLabs terms; commercial use depends on your plan.",
        verified=False, setup="Create an API key on a plan that includes Music.",
    ))

    register(ProviderSpec(
        V, "system_tts", "System speech (built-in)", "Your operating system's speech engine. Spoken, robotic delivery. Not an AI model.",
        lambda c: SystemSpeechProvider(rate=int(c.options.get("rate", 185))), is_ai=False,
        default_model="os-speech-engine", capabilities=("speech",), packages=("pyttsx3",),
        license="Uses voices installed with the OS.", setup="pip install pyttsx3 (Linux also needs espeak-ng).",
    ))
    register(ProviderSpec(
        V, "openai_speech", "OpenAI-compatible speech", "Any /audio/speech server: OpenAI, Kokoro-FastAPI, LocalAI.",
        lambda c: OpenAISpeechProvider(
            base_url=c.base_url, api_key=c.api_key, model=c.model, default_voice=c.options.get("default_voice", "alloy"),
            stock_voices=tuple(c.options.get("voices", ("alloy", "echo", "fable", "onyx", "nova", "shimmer"))),
        ),
        local=False, needs_base_url=True, needs_model=True, default_base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini-tts", capabilities=("speech",), license="Depends on the service.", verified=False,
    ))
    register(ProviderSpec(
        V, "elevenlabs", "ElevenLabs (hosted)", "Speech, instant voice cloning, and speech-to-speech conversion that keeps a sung melody.",
        lambda c: ElevenLabsVoiceProvider(base_url=c.base_url, api_key=c.api_key, model=c.model),
        local=False, needs_api_key=True, default_base_url="https://api.elevenlabs.io", default_model="eleven_multilingual_v2",
        capabilities=("speech", "cloning", "conversion"), license="ElevenLabs terms. Cloning requires the voice owner's consent.",
        verified=False,
    ))
    register(ProviderSpec(
        V, "chatterbox", "Chatterbox (local)", "Zero-shot speech cloning from a reference recording. Speech only, not singing.",
        lambda c: ChatterboxProvider(), default_model="ResembleAI/chatterbox", capabilities=("speech", "cloning"),
        packages=("chatterbox", "torch"), hardware="GPU with 6 GB+ VRAM recommended", license="MIT.", commercial_use=True,
        verified=False, setup="pip install chatterbox-tts (weights download on first use, about 2 GB).",
    ))

    image_params = ("prompt", "width", "height", "seed")
    register(ProviderSpec(
        I, "typographic", "Built-in title cards", "Typographic artwork drawn with Pillow. Not an AI model.",
        lambda c: TypographicProvider(), is_ai=False, default_model="troll-cards-1", params=image_params,
        packages=("PIL", "numpy"), license="MIT (part of this project).", commercial_use=True,
    ))
    register(ProviderSpec(
        I, "pollinations", "Pollinations (free, hosted)", "Hosted image models. Keyless but rate-limited; prompts leave this machine.",
        lambda c: PollinationsImageProvider(base_url=c.base_url, api_key=c.api_key, model=c.model),
        local=False, default_base_url="https://image.pollinations.ai", default_model="flux",
        suggested_models=("flux", "turbo"), params=image_params, license="Pollinations terms of service.",
    ))
    register(ProviderSpec(
        I, "openai_images", "OpenAI-compatible images", "Any /images/generations server, including OpenAI.",
        lambda c: OpenAIImagesProvider(base_url=c.base_url, api_key=c.api_key, model=c.model),
        local=False, needs_base_url=True, needs_model=True, default_base_url="https://api.openai.com/v1",
        default_model="gpt-image-1", params=("prompt",), license="Depends on the service.", verified=False,
    ))
    register(ProviderSpec(
        I, "comfyui", "ComfyUI (local server)", "Your own ComfyUI with a Stable Diffusion checkpoint.",
        lambda c: ComfyUIProvider(base_url=c.base_url, model=c.model), needs_model=True,
        default_base_url="http://127.0.0.1:8188", params=image_params, hardware="GPU with 6 GB+ VRAM",
        license="ComfyUI is GPL-3.0. Each checkpoint has its own licence.", verified=False,
        setup="Start ComfyUI and set the model to a checkpoint file name, e.g. sd_xl_base_1.0.safetensors",
    ))


_register_all()
