"""Voice adapters.

None of these sing. They produce *spoken* delivery, which the studio places on
the beat grid for a rap-style vocal. Sung vocals come from a music model that
accepts lyrics (see ``AceStepProvider.generate_song``), optionally followed by
voice conversion to an authorized voice.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
from pathlib import Path

from ..errors import ProviderNotConfiguredError, ProviderResponseError, ProviderUnavailableError
from ..types import SpeechLine
from ._http import HttpAdapter
from .base import ProviderInfo, ProviderKind, ProviderStatus, VoiceCapabilities, VoiceProvider

_WORKER = [sys.executable, "-m", "troll_music_ai.providers._speech_worker"]


class SystemSpeechProvider(VoiceProvider):
    """The operating system's speech engine (SAPI, NSSpeech or eSpeak).

    Built in, offline and robotic. Not an AI voice model and not a clone.
    """

    def __init__(self, *, rate: int = 185) -> None:
        self._rate = rate

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="system_tts", kind=ProviderKind.VOICE, model="os-speech-engine", is_ai=False)

    @property
    def capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities()

    def _run(self, *args: str, timeout: float = 300) -> str:
        try:
            done = subprocess.run([*_WORKER, *args], capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ProviderUnavailableError("The system speech engine timed out.") from exc
        if done.returncode != 0:
            if "No module named 'pyttsx3'" in done.stderr:
                raise ProviderNotConfiguredError("System speech needs pyttsx3: pip install pyttsx3")
            raise ProviderUnavailableError(
                "The system speech engine failed: " + (done.stderr.strip().splitlines() or ["unknown error"])[-1][:200]
            )
        return done.stdout

    async def voices(self) -> list[str]:
        return json.loads(await asyncio.to_thread(self._run, "voices", timeout=30))

    async def check(self) -> ProviderStatus:
        try:
            names = await self.voices()
        except Exception as exc:  # check() must not raise
            return ProviderStatus(ok=False, detail=str(exc))
        if not names:
            return ProviderStatus(ok=False, detail="No system voices are installed.")
        return ProviderStatus(ok=True, detail=f"{len(names)} system voice(s). Spoken delivery only.", models=names)

    async def synthesize_lines(self, lines: list[SpeechLine], out_dir: Path) -> list[Path]:
        outputs = [out_dir / f"line_{index:03d}.wav" for index in range(len(lines))]
        job = out_dir / "speech_job.json"
        job.write_text(
            json.dumps(
                {
                    "rate": self._rate,
                    "lines": [
                        {"text": line.text, "voice": line.voice, "out": str(path)}
                        for line, path in zip(lines, outputs)
                    ],
                }
            ),
            encoding="utf-8",
        )
        await asyncio.to_thread(self._run, "speak", str(job))
        missing = [path.name for path in outputs if not path.exists() or path.stat().st_size < 100]
        if missing:
            raise ProviderResponseError(f"The system speech engine produced no audio for {len(missing)} line(s).")
        return outputs


class OpenAISpeechProvider(HttpAdapter, VoiceProvider):
    """Any server with the OpenAI ``/audio/speech`` endpoint: OpenAI itself,
    Kokoro-FastAPI, openedai-speech, LocalAI and similar."""

    name = "openai_speech"

    def __init__(self, *, model: str, default_voice: str = "alloy", stock_voices: tuple[str, ...] = (), **kwargs) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._default_voice = default_voice
        self._stock_voices = list(stock_voices) or [default_voice]

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, kind=ProviderKind.VOICE, model=self._model, endpoint=self._base_url)

    @property
    def capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities()

    async def voices(self) -> list[str]:
        return self._stock_voices

    async def check(self) -> ProviderStatus:
        ok, detail, _ = await self._probe("/models")
        return ProviderStatus(ok=ok, detail=detail)

    async def synthesize_lines(self, lines: list[SpeechLine], out_dir: Path) -> list[Path]:
        outputs = []
        for index, line in enumerate(lines):
            response = await self._send(
                "POST",
                "/audio/speech",
                json={
                    "model": self._model,
                    "input": line.text,
                    "voice": line.voice or self._default_voice,
                    "response_format": "wav",
                },
            )
            path = out_dir / f"line_{index:03d}.wav"
            path.write_bytes(response.content)
            outputs.append(path)
        return outputs


class ElevenLabsVoiceProvider(HttpAdapter, VoiceProvider):
    """ElevenLabs: speech, instant voice cloning and speech-to-speech conversion.

    Conversion keeps the melody and timing of the source recording, so a sung
    guide vocal converted to an authorized voice stays sung.
    """

    name = "elevenlabs"

    def __init__(self, *, model: str = "eleven_multilingual_v2", sts_model: str = "eleven_multilingual_sts_v2", **kwargs) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._sts_model = sts_model

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key or ""}

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, kind=ProviderKind.VOICE, model=self._model, endpoint=self._base_url)

    @property
    def capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities(cloning=True, conversion=True)

    async def _voice_ids(self) -> dict[str, str]:
        data = (await self._send("GET", "/v1/voices")).json()
        return {voice["name"]: voice["voice_id"] for voice in data.get("voices", [])}

    async def voices(self) -> list[str]:
        return list(await self._voice_ids())

    async def check(self) -> ProviderStatus:
        ok, detail, _ = await self._probe("/v1/voices")
        return ProviderStatus(ok=ok, detail=detail)

    async def synthesize_lines(self, lines: list[SpeechLine], out_dir: Path) -> list[Path]:
        known = await self._voice_ids()
        if not known:
            raise ProviderResponseError("The ElevenLabs account has no voices.")
        fallback = next(iter(known.values()))
        outputs = []
        for index, line in enumerate(lines):
            # `voice` is a stock voice name or the id of a cloned voice.
            voice_id = known.get(line.voice or "", line.voice if line.voice in known.values() else None) or (
                line.voice if line.voice and len(line.voice) >= 16 else fallback
            )
            response = await self._send(
                "POST",
                f"/v1/text-to-speech/{voice_id}",
                params={"output_format": "mp3_44100_128"},
                json={"text": line.text, "model_id": self._model},
            )
            path = out_dir / f"line_{index:03d}.mp3"
            path.write_bytes(response.content)
            outputs.append(path)
        return outputs

    async def create_voice(self, name: str, sample_path: Path) -> str:
        with open(sample_path, "rb") as handle:
            response = await self._send(
                "POST", "/v1/voices/add", data={"name": name}, files={"files": (sample_path.name, handle.read())}
            )
        voice_id = response.json().get("voice_id")
        if not voice_id:
            raise ProviderResponseError("ElevenLabs did not return a voice id.")
        return voice_id

    async def delete_voice(self, provider_voice_id: str) -> None:
        await self._send("DELETE", f"/v1/voices/{provider_voice_id}")

    async def convert_voice(self, source_path: Path, provider_voice_id: str, out_path: Path) -> Path:
        with open(source_path, "rb") as handle:
            response = await self._send(
                "POST",
                f"/v1/speech-to-speech/{provider_voice_id}",
                params={"output_format": "mp3_44100_128"},
                data={"model_id": self._sts_model},
                files={"audio": (source_path.name, handle.read())},
            )
        target = out_path.with_suffix(".mp3")
        target.write_bytes(response.content)
        return target


class ChatterboxProvider(VoiceProvider):
    """Resemble AI's Chatterbox, on this machine. Zero-shot speech cloning from
    a reference recording. Speech only.

    NOTE: written against Chatterbox's documented Python API but not yet run
    by the maintainers. Needs ``pip install chatterbox-tts`` and a GPU.
    """

    _model = None
    _lock = threading.Lock()

    def __init__(self, *, device: str | None = None) -> None:
        self._device = device

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="chatterbox", kind=ProviderKind.VOICE, model="ResembleAI/chatterbox")

    @property
    def capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities(cloning=True)

    async def voices(self) -> list[str]:
        return ["default"]

    async def check(self) -> ProviderStatus:
        try:
            import chatterbox  # noqa: F401
            import torch
        except ImportError:
            return ProviderStatus(ok=False, detail="chatterbox-tts is not installed: pip install chatterbox-tts")
        device = "GPU" if torch.cuda.is_available() else "CPU (slow)"
        return ProviderStatus(ok=True, detail=f"Installed. Runs on {device}. Weights download on first use.")

    def _load(self):
        with self._lock:
            if ChatterboxProvider._model is None:
                try:
                    import torch
                    from chatterbox.tts import ChatterboxTTS
                except ImportError as exc:
                    raise ProviderNotConfiguredError("Chatterbox needs: pip install chatterbox-tts") from exc
                device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
                ChatterboxProvider._model = ChatterboxTTS.from_pretrained(device=device)
            return ChatterboxProvider._model

    async def synthesize_lines(self, lines: list[SpeechLine], out_dir: Path) -> list[Path]:
        def work() -> list[Path]:
            from .procedural import write_wav

            model = self._load()
            outputs = []
            for index, line in enumerate(lines):
                audio = model.generate(line.text, audio_prompt_path=line.sample_path)
                path = out_dir / f"line_{index:03d}.wav"
                write_wav(path, audio.squeeze().cpu().numpy(), model.sr)
                outputs.append(path)
            return outputs

        return await asyncio.to_thread(work)

    # Zero-shot: the stored sample is the voice, so there is nothing to register.
    async def create_voice(self, name: str, sample_path: Path) -> str:
        return "zero-shot"

    async def delete_voice(self, provider_voice_id: str) -> None:
        return None
