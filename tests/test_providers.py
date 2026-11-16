"""Provider registry and adapters, with the network mocked.

Passing here means the adapter sends the request it should and handles the
answers it might get. It does not mean the real service or model was called.
"""

from __future__ import annotations

import asyncio
import json
import wave

import httpx
import numpy as np
import pytest

from troll_music_ai import ProviderNotConfiguredError, ProviderResponseError, ProviderUnavailableError
from troll_music_ai.providers import ProviderConfig, ProviderKind, registry
from troll_music_ai.providers.images import PollinationsImageProvider, TypographicProvider
from troll_music_ai.providers.music_models import AceStepProvider, ElevenLabsMusicProvider, MusicGenProvider
from troll_music_ai.providers.procedural import SR, ProceduralBeatProvider
from troll_music_ai.providers.voice import ElevenLabsVoiceProvider, OpenAISpeechProvider
from troll_music_ai.types import BeatRequest, ImageRequest, SongRequest, SpeechLine


def run(coro):
    return asyncio.run(coro)


def transport(handler):
    return httpx.MockTransport(handler)


# -------------------------------- registry --------------------------------- #


def test_every_spec_is_complete_and_honest():
    names = {(spec.kind.value, spec.name) for spec in registry.specs()}
    assert {("text", "ollama"), ("music", "procedural"), ("music", "musicgen"), ("voice", "system_tts"), ("image", "typographic")} <= names
    for spec in registry.specs():
        assert spec.label and spec.description
        if not spec.local or spec.is_ai:
            assert spec.license, f"{spec.name} has no licence note"
    built_ins = [s for s in registry.specs() if s.name in ("procedural", "system_tts", "typographic")]
    assert all(not s.is_ai and not s.is_mock for s in built_ins)
    # Weights for MusicGen are non-commercial, and the registry says so.
    assert registry.get_spec(ProviderKind.MUSIC, "musicgen").commercial_use is False


def test_build_refuses_incomplete_configuration():
    assert registry.build(ProviderKind.TEXT, ProviderConfig(provider="none")) is None
    with pytest.raises(ProviderNotConfiguredError, match="Unknown TROLL_MUSIC_PROVIDER"):
        registry.build(ProviderKind.MUSIC, ProviderConfig(provider="suno"))
    with pytest.raises(ProviderNotConfiguredError, match="TROLL_VOICE_API_KEY"):
        registry.build(ProviderKind.VOICE, ProviderConfig(provider="elevenlabs"))
    with pytest.raises(ProviderNotConfiguredError, match="TROLL_IMAGE_MODEL"):
        registry.build(ProviderKind.IMAGE, ProviderConfig(provider="comfyui"))
    ollama = registry.build(ProviderKind.TEXT, ProviderConfig(provider="ollama"))
    assert ollama.info.model == "llama3.2" and ollama.info.endpoint == "http://localhost:11434/v1"


def test_a_missing_python_package_is_reported_with_the_fix(monkeypatch):
    spec = registry.get_spec(ProviderKind.VOICE, "chatterbox")
    monkeypatch.setattr(type(spec), "missing_packages", lambda self: ["chatterbox"] if self.name == "chatterbox" else [])
    with pytest.raises(ProviderNotConfiguredError, match="not installed: chatterbox.*pip install"):
        registry.build(ProviderKind.VOICE, ProviderConfig(provider="chatterbox"))


# ----------------------------- built-in engines ----------------------------- #


def test_procedural_beat_has_the_exact_length_and_audible_kicks_on_the_beat(tmp_path):
    provider = ProceduralBeatProvider()
    assert provider.info.is_ai is False and provider.capabilities.exact_bpm
    path = run(provider.generate_instrumental(BeatRequest(genre="edm", bpm=120, duration_seconds=8), tmp_path / "b.wav", 7))
    with wave.open(str(path)) as handle:
        assert handle.getframerate() == SR
        frames = handle.getnframes()
        samples = np.frombuffer(handle.readframes(frames), dtype="<i2").reshape(-1, handle.getnchannels()).mean(axis=1)
    assert abs(frames / SR - 8) < 0.05
    assert np.abs(samples).max() > 3000  # not silence
    # Four-on-the-floor at 120 BPM: energy right after each beat beats the gap before it.
    beat = SR // 2
    hits = [np.abs(samples[i * beat : i * beat + 2000]).mean() > np.abs(samples[i * beat - 3000 : i * beat - 1000]).mean() for i in range(1, 12)]
    assert sum(hits) >= 9


def test_procedural_beats_are_reproducible_per_seed(tmp_path):
    provider = ProceduralBeatProvider()
    request = BeatRequest(genre="trap", bpm=140, duration_seconds=5)
    a = run(provider.generate_instrumental(request, tmp_path / "a.wav", 1)).read_bytes()
    b = run(provider.generate_instrumental(request, tmp_path / "b.wav", 1)).read_bytes()
    c = run(provider.generate_instrumental(request, tmp_path / "c.wav", 2)).read_bytes()
    assert a == b and a != c


def test_typographic_cards_have_the_requested_size(tmp_path):
    from PIL import Image

    path = run(TypographicProvider().generate_image(ImageRequest(prompt="cover", width=720, height=1280, title="Layaway"), tmp_path / "c.png"))
    assert Image.open(path).size == (720, 1280)


def test_musicgen_never_downloads_weights_on_its_own(monkeypatch, tmp_path):
    pytest.importorskip("transformers")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    provider = MusicGenProvider(model="facebook/definitely-not-downloaded")
    status = run(provider.check())
    assert status.ok is False and "download_models.py" in status.detail
    with pytest.raises(ProviderUnavailableError, match="download_models.py"):
        run(provider.generate_instrumental(BeatRequest(duration_seconds=5), tmp_path / "x.wav", 0))


# ------------------------------ hosted adapters ----------------------------- #


def test_elevenlabs_music_request_shape_and_errors(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["key"], seen["body"] = str(request.url), request.headers.get("xi-api-key"), json.loads(request.content)
        return httpx.Response(200, content=b"ID3fake-mp3-bytes")

    provider = ElevenLabsMusicProvider(base_url="https://api.elevenlabs.io", api_key="k", model="music_v1", transport=transport(handler))
    path = run(provider.generate_instrumental(BeatRequest(genre="drill", bpm=140, duration_seconds=12), tmp_path / "out", 3))
    assert path.suffix == ".mp3" and path.read_bytes().startswith(b"ID3")
    assert "/v1/music" in seen["url"] and seen["key"] == "k"
    assert seen["body"]["music_length_ms"] == 12000 and seen["body"]["force_instrumental"] is True
    assert "drill" in seen["body"]["prompt"] and "140 BPM" in seen["body"]["prompt"]

    denied = ElevenLabsMusicProvider(base_url="https://api.elevenlabs.io", api_key="bad", model="music_v1", transport=transport(lambda r: httpx.Response(401, json={"detail": {"message": "Invalid API key"}})))
    with pytest.raises(ProviderResponseError) as error:
        run(denied.generate_instrumental(BeatRequest(), tmp_path / "x", 0))
    assert error.value.status_code == 401 and "bad" not in error.value.message


def test_acestep_submits_polls_and_downloads(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/release_task":
            body = json.loads(request.content)
            assert "[Verse 1]" in body["lyrics"] and body["audio_duration"] == 30
            return httpx.Response(200, json={"code": 200, "data": {"task_id": "t1"}})
        if request.url.path == "/query_result":
            done = calls.count("/query_result") > 1
            result = json.dumps([{"file": "/v1/audio?path=song.mp3", "status": 1}]) if done else "[]"
            return httpx.Response(200, json={"code": 200, "data": [{"task_id": "t1", "status": 1 if done else 0, "result": result}]})
        return httpx.Response(200, content=b"ID3sung")

    provider = AceStepProvider(base_url="http://ace.test", poll_seconds=0, transport=transport(handler))
    assert provider.capabilities.with_vocals is True
    path = run(provider.generate_song(SongRequest(lyrics_text="[Verse 1]\nhello", style_prompt="drill", duration_seconds=30), tmp_path / "song", 1))
    assert path.read_bytes() == b"ID3sung" and calls.count("/query_result") == 2

    down = AceStepProvider(base_url="http://ace.test", transport=transport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("refused"))))
    assert run(down.check()).ok is False
    with pytest.raises(ProviderUnavailableError):
        run(down.generate_instrumental(BeatRequest(), tmp_path / "x", 0))


def test_openai_speech_writes_one_file_per_line(tmp_path):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=b"RIFFfake")

    provider = OpenAISpeechProvider(base_url="http://tts.test/v1", api_key=None, model="kokoro", default_voice="af_sky", transport=transport(handler))
    assert provider.capabilities.singing is False and provider.capabilities.cloning is False
    paths = run(provider.synthesize_lines([SpeechLine(text="one"), SpeechLine(text="two", voice="am_adam")], tmp_path))
    assert len(paths) == 2 and all(p.read_bytes() == b"RIFFfake" for p in paths)
    assert [(b["input"], b["voice"], b["model"]) for b in bodies] == [("one", "af_sky", "kokoro"), ("two", "am_adam", "kokoro")]


def test_elevenlabs_voice_clone_convert_and_delete(tmp_path):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/v1/voices/add":
            assert b"sample.wav" in request.content
            return httpx.Response(200, json={"voice_id": "v123"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, content=b"ID3converted")

    provider = ElevenLabsVoiceProvider(base_url="https://api.elevenlabs.io", api_key="k", model="eleven_multilingual_v2", transport=transport(handler))
    capabilities = provider.capabilities
    assert capabilities.cloning and capabilities.conversion and not capabilities.singing
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"RIFF....")
    assert run(provider.create_voice("Sam", sample)) == "v123"
    out = run(provider.convert_voice(sample, "v123", tmp_path / "converted"))
    assert out.read_bytes() == b"ID3converted"
    run(provider.delete_voice("v123"))
    assert ("POST", "/v1/speech-to-speech/v123") in seen and ("DELETE", "/v1/voices/v123") in seen


def test_pollinations_images_retry_on_rate_limits_then_give_up_cleanly(tmp_path):
    attempts = []

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts.append(request.url)
        if len(attempts) < 3:
            return httpx.Response(503, text="queue full")
        return httpx.Response(200, content=b"\xff\xd8\xffjpeg", headers={"content-type": "image/jpeg"})

    provider = PollinationsImageProvider(base_url="https://image.pollinations.ai", model="flux", retry_seconds=0, transport=transport(flaky))
    path = run(provider.generate_image(ImageRequest(prompt="a llama on a jet ski", width=512, height=512, seed=9), tmp_path / "img.png"))
    assert path.suffix == ".jpg" and len(attempts) == 3
    assert "llama" in str(attempts[0]) and attempts[0].params["width"] == "512" and attempts[0].params["seed"] == "9"

    busy = PollinationsImageProvider(base_url="https://image.pollinations.ai", model="flux", retries=2, retry_seconds=0, transport=transport(lambda r: httpx.Response(503)))
    with pytest.raises((ProviderResponseError, ProviderUnavailableError)):
        run(busy.generate_image(ImageRequest(prompt="anything"), tmp_path / "no.png"))
