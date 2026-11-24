"""AI music adapters: MusicGen (local), ACE-Step (local server), ElevenLabs Music (hosted)."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from ..errors import ProviderNotConfiguredError, ProviderResponseError, ProviderUnavailableError
from ..types import BeatRequest, SongRequest
from ._http import HttpAdapter
from .base import MusicCapabilities, MusicGenerationProvider, ProviderInfo, ProviderKind, ProviderStatus


class MusicGenProvider(MusicGenerationProvider):
    """Meta's MusicGen through ``transformers``, on this machine.

    Weights are CC-BY-NC 4.0 (non-commercial). They are never downloaded
    implicitly: run ``python scripts/download_models.py musicgen`` first.
    """

    MAX_SECONDS = 30.0  # the model's context is about 30 s of audio
    _loaded: dict[str, tuple] = {}
    _lock = threading.Lock()

    def __init__(self, *, model: str = "facebook/musicgen-small", device: str | None = None, allow_download: bool = False) -> None:
        self._model = model
        self._device = device
        self._allow_download = allow_download

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="musicgen", kind=ProviderKind.MUSIC, model=self._model)

    @property
    def capabilities(self) -> MusicCapabilities:
        return MusicCapabilities(max_duration_seconds=self.MAX_SECONDS)

    def _load(self):
        with self._lock:
            if self._model in self._loaded:
                return self._loaded[self._model]
            try:
                import torch
                from transformers import AutoProcessor, MusicgenForConditionalGeneration
            except ImportError as exc:
                raise ProviderNotConfiguredError(
                    "MusicGen needs PyTorch and transformers: pip install torch transformers "
                    "(see docs/models.md for the CUDA build)."
                ) from exc
            device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
            try:
                options = {"local_files_only": not self._allow_download}
                processor = AutoProcessor.from_pretrained(self._model, **options)
                model = MusicgenForConditionalGeneration.from_pretrained(self._model, **options).to(device)
            except OSError as exc:
                raise ProviderUnavailableError(
                    f"The weights for {self._model} are not on this machine. "
                    "Run: python scripts/download_models.py musicgen"
                ) from exc
            self._loaded[self._model] = (processor, model, device, torch)
            return self._loaded[self._model]

    async def check(self) -> ProviderStatus:
        try:
            import torch
            import transformers  # noqa: F401
            from huggingface_hub import try_to_load_from_cache
        except ImportError:
            return ProviderStatus(ok=False, detail="PyTorch or transformers is not installed.")
        if not isinstance(try_to_load_from_cache(self._model, "config.json"), str):
            return ProviderStatus(
                ok=False,
                detail=f"Weights for {self._model} are not downloaded. Run: python scripts/download_models.py musicgen",
            )
        device = "GPU: " + torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU (slow)"
        return ProviderStatus(ok=True, detail=f"Weights present. Will run on {device}.")

    async def generate_instrumental(self, request: BeatRequest, out_path: Path, seed: int) -> Path:
        def work() -> Path:
            from .procedural import write_wav

            processor, model, device, torch = self._load()
            torch.manual_seed(seed)
            inputs = processor(text=[request.prompt()], padding=True, return_tensors="pt").to(device)
            seconds = min(request.duration_seconds, self.MAX_SECONDS)
            with torch.no_grad():
                audio = model.generate(**inputs, do_sample=True, guidance_scale=3.0, max_new_tokens=int(seconds * 50))
            target = out_path.with_suffix(".wav")
            write_wav(target, audio[0, 0].float().cpu().numpy(), model.config.audio_encoder.sampling_rate)
            return target

        return await asyncio.to_thread(work)


class AceStepProvider(HttpAdapter, MusicGenerationProvider):
    """Client for an ACE-Step 1.5 API server (``uv run acestep-api``, port 8001).

    ACE-Step can sing supplied lyrics, so it also serves full-song generation.
    """

    name = "acestep"

    def __init__(self, *, model: str | None = None, poll_seconds: float = 2.0, **kwargs) -> None:
        kwargs.setdefault("timeout", 900.0)
        super().__init__(**kwargs)
        self._model = model
        self._poll_seconds = poll_seconds

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, kind=ProviderKind.MUSIC, model=self._model or "acestep-v15", endpoint=self._base_url)

    @property
    def capabilities(self) -> MusicCapabilities:
        return MusicCapabilities(exact_duration=True, max_duration_seconds=600, with_vocals=True, key_control=True)

    async def check(self) -> ProviderStatus:
        ok, detail, _ = await self._probe("/health")
        return ProviderStatus(ok=ok, detail=detail)

    async def _run(self, payload: dict, out_path: Path, seed: int) -> Path:
        payload |= {"batch_size": 1, "audio_format": "wav", "use_random_seed": False, "seed": seed}
        if self._api_key:
            payload["ai_token"] = self._api_key
        if self._model:
            payload["model"] = self._model
        submitted = (await self._send("POST", "/release_task", json=payload)).json()
        task_id = (submitted.get("data") or {}).get("task_id")
        if not task_id:
            raise ProviderResponseError(f"ACE-Step did not return a task id: {submitted.get('error')}")

        waited = 0.0
        while waited < self._timeout:
            await asyncio.sleep(self._poll_seconds)
            waited += self._poll_seconds
            rows = (await self._send("POST", "/query_result", json={"task_id_list": [task_id]})).json().get("data") or []
            row = rows[0] if rows else {}
            if row.get("status") == 2:
                reason = row.get("error") or row.get("message") or "no reason given"
                raise ProviderResponseError(f"ACE-Step reported that generation failed ({str(reason)[:200]}).")
            if row.get("status") == 1:
                results = json.loads(row["result"]) if isinstance(row.get("result"), str) else row.get("result") or []
                if not results or not results[0].get("file"):
                    raise ProviderResponseError("ACE-Step finished without an audio file.")
                audio = await self._send("GET", results[0]["file"])
                target = out_path.with_suffix(".wav")
                target.write_bytes(audio.content)
                return target
        raise ProviderUnavailableError(f"ACE-Step did not finish within {self._timeout:.0f}s.")

    async def generate_instrumental(self, request: BeatRequest, out_path: Path, seed: int) -> Path:
        payload = {"prompt": request.prompt(), "lyrics": "[Instrumental]", "audio_duration": request.duration_seconds}
        if request.bpm:
            payload["bpm"] = request.bpm
        if request.key:
            payload["key_scale"] = request.key
        return await self._run(payload, out_path, seed)

    async def generate_song(self, request: SongRequest, out_path: Path, seed: int) -> Path:
        payload = {
            "prompt": request.style_prompt,
            "lyrics": request.lyrics_text,
            "audio_duration": request.duration_seconds,
            "vocal_language": request.language,
            # The 5 Hz language model plans melody and phrasing from the lyrics
            # before the DiT renders audio; ACE-Step recommends it for songs.
            "thinking": True,
            "time_signature": "4",
        }
        if request.bpm:
            payload["bpm"] = request.bpm
        return await self._run(payload, out_path, seed)


# --------------------------- shared song planning --------------------------- #

_SECTION_WEIGHT = {"intro": 0.6, "outro": 0.6, "chorus": 1.0, "hook": 1.0}
MAX_LINES_PER_SECTION = 30
MAX_LINE_CHARS = 200


def plan_sections(request: SongRequest, *, min_ms: int = 3000, max_ms: int = 120_000) -> list[tuple[str, list[str], int]]:
    """Split ``request.duration_seconds`` across the sections by how much each one sings.

    Returns ``(label, lines, duration_ms)`` per section, with lines clipped to
    the hosted models' limits (30 lines, 200 characters each).
    """
    parts = [p for p in request.sections if p.lines] or []
    if not parts:
        return []
    weights = []
    for part in parts:
        kind = part.label.split()[0].lower()
        weights.append(max(len(part.lines), 2) * _SECTION_WEIGHT.get(kind, 1.0))
    total_ms = int(request.duration_seconds * 1000)
    plan = []
    for part, weight in zip(parts, weights):
        ms = int(total_ms * weight / sum(weights))
        lines = [line.strip()[:MAX_LINE_CHARS] for line in part.lines if line.strip()][:MAX_LINES_PER_SECTION]
        plan.append((part.label.strip()[:100], lines, max(min_ms, min(max_ms, ms))))
    return plan


def _styles(text: str | None) -> list[str]:
    return [s.strip() for s in (text or "").split(",") if s.strip()]


class ElevenLabsMusicProvider(HttpAdapter, MusicGenerationProvider):
    """ElevenLabs Music (``POST /v1/music``). Hosted; the Music API needs a paid plan.

    Songs are sent as a composition plan: one section per lyric section, with
    its lines and a share of the duration, so the model is given the exact
    words in the exact order. Whether every word is sung as written is up to
    the model and is not verified here.

    ``music_v1`` takes ``sections``; ``music_v2`` and ``music_v2_5`` take
    ``chunks`` (and are better at fast rap, per ElevenLabs).
    """

    name = "elevenlabs_music"
    RETRY_STATUSES = (429, 500, 502, 503, 504)

    def __init__(self, *, model: str = "music_v1", retries: int = 2, retry_wait: float = 5.0, sleep=asyncio.sleep, **kwargs) -> None:
        kwargs.setdefault("timeout", 300.0)
        super().__init__(**kwargs)
        self._model = model or "music_v1"
        self._retries = retries
        self._retry_wait = retry_wait
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key or ""}

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, kind=ProviderKind.MUSIC, model=self._model, endpoint=self._base_url)

    @property
    def capabilities(self) -> MusicCapabilities:
        return MusicCapabilities(exact_duration=True, max_duration_seconds=300, with_vocals=True)

    async def check(self) -> ProviderStatus:
        ok, detail, _ = await self._probe("/v1/user")
        return ProviderStatus(ok=ok, detail=detail)

    async def _compose(self, body: dict, out_path: Path) -> Path:
        """POST /v1/music, retrying rate limits and server errors (not timeouts:
        a request that timed out may still have been charged)."""
        attempt = 0
        while True:
            try:
                response = await self._send("POST", "/v1/music", params={"output_format": "mp3_44100_128"}, json=body)
                break
            except ProviderResponseError as exc:
                status = getattr(exc, "status_code", None)
                if status in (401, 403) and "plan" not in exc.message.lower():
                    raise ProviderNotConfiguredError("ElevenLabs rejected the API key (check TROLL_MUSIC_API_KEY or AI Settings).") from exc
                if status == 402 or (status in (401, 403) and "plan" in exc.message.lower()):
                    raise ProviderNotConfiguredError(
                        "ElevenLabs refused the request for this account: the Music API needs a paid plan with enough credits. "
                        f"({exc.message})"
                    ) from exc
                if status not in self.RETRY_STATUSES or attempt >= self._retries:
                    raise
            attempt += 1
            await self._sleep(self._retry_wait * attempt)
        kind = response.headers.get("content-type", "")
        if not response.content or kind.startswith(("application/json", "text/")):
            raise ProviderResponseError(f"ElevenLabs answered without audio ({kind or 'no content type'}): {response.text[:200]}")
        target = out_path.with_suffix(".mp3")
        target.write_bytes(response.content)
        return target

    async def generate_instrumental(self, request: BeatRequest, out_path: Path, seed: int) -> Path:
        body = {
            "prompt": request.prompt()[:4000],
            "music_length_ms": int(max(3, min(300, request.duration_seconds)) * 1000),
            "force_instrumental": True,
            "model_id": self._model,
            "seed": seed % 2147483647,
        }
        return await self._compose(body, out_path)

    def song_body(self, request: SongRequest) -> dict:
        """The JSON sent for a full song. Public so it can be inspected in tests."""
        styles = _styles(request.style_prompt) or ["hip-hop", "rap vocals"]
        negatives = _styles(request.negative_style)
        plan = plan_sections(request)
        if not plan:  # no structured sections: send the lyrics as one prompt
            return {
                "prompt": f"{', '.join(styles)}. Lyrics:\n{request.lyrics_text}"[:4000],
                "music_length_ms": int(request.duration_seconds * 1000),
                "model_id": self._model,
            }
        local = lambda label: ["catchy hook", "full energy"] if label.lower().startswith(("chorus", "hook")) else []  # noqa: E731
        if self._model.startswith("music_v2"):
            chunks = []
            for index, (label, lines, ms) in enumerate(plan):
                chunks.append({
                    "text": "\n".join([f"[{label}]", *lines]),
                    "duration_ms": ms,
                    "positive_styles": [*styles, "great production quality"] if index == 0 else [*styles[:3], *local(label)],
                    "negative_styles": negatives,
                    "context_adherence": "high",
                })
            return {"composition_plan": {"chunks": chunks}, "model_id": self._model}
        sections = [
            {"section_name": label, "positive_local_styles": local(label), "negative_local_styles": [], "duration_ms": ms, "lines": lines}
            for label, lines, ms in plan
        ]
        return {
            "composition_plan": {"positive_global_styles": styles, "negative_global_styles": negatives, "sections": sections},
            "model_id": self._model,
            "respect_sections_durations": False,
        }

    async def generate_song(self, request: SongRequest, out_path: Path, seed: int) -> Path:
        return await self._compose(self.song_body(request), out_path)
