"""Integration tests against REAL providers. Skipped unless asked for:

    TROLL_RUN_INTEGRATION=1 pytest tests/integration -v

Each test skips itself, with the reason, when its provider is not available on
this machine (no weights, no server, no network, no key). A skip is not a pass.

Optional environment:
    TROLL_TEST_OLLAMA_MODEL      model to use with a local Ollama (default llama3.2)
    TROLL_TEST_MUSICGEN_MODEL    default facebook/musicgen-small (weights must be downloaded)
    TROLL_TEST_ACESTEP_URL       ACE-Step API server, e.g. http://localhost:8001
    TROLL_TEST_ELEVENLABS_KEY    ElevenLabs API key (uses paid credits)
"""

from __future__ import annotations

import asyncio
import os

import pytest

from backend.audio import ffmpeg
from troll_music_ai import LyricsRequest, TrollMusicError
from troll_music_ai.lyrics import LyricsService
from troll_music_ai.providers import ProviderConfig, ProviderKind, registry
from troll_music_ai.types import BeatRequest, ImageRequest, SongRequest, SpeechLine

pytestmark = pytest.mark.skipif(
    os.environ.get("TROLL_RUN_INTEGRATION") != "1", reason="set TROLL_RUN_INTEGRATION=1 to call real providers"
)


def run(coro):
    return asyncio.run(coro)


def build(kind: str, name: str, **config):
    return registry.build(ProviderKind(kind), ProviderConfig(provider=name, **config))


def require(provider) -> None:
    status = run(provider.check())
    if not status.ok:
        pytest.skip(f"{provider.info.name} is not available here: {status.detail}")


def write_lyrics(provider) -> None:
    lyrics = run(LyricsService(provider).generate(LyricsRequest(prompt="my flatmate never does the dishes", genre="drill", length="short", verses=1)))
    lines = [line for section in lyrics.sections for line in section.lines]
    print(f"\n[{provider.info.name} / {lyrics.meta.model}] {lyrics.title}: {lines[:3]}")
    assert lyrics.title and len(lines) >= 6 and lyrics.meta.is_mock is False
    assert any(section.type == "chorus" for section in lyrics.sections)


def test_lyrics_with_pollinations():
    provider = build("text", "pollinations")
    require(provider)
    write_lyrics(provider)


def test_lyrics_with_ollama():
    provider = build("text", "ollama", model=os.environ.get("TROLL_TEST_OLLAMA_MODEL", "llama3.2"))
    require(provider)
    write_lyrics(provider)


def test_system_speech_produces_audible_audio(tmp_path):
    provider = build("voice", "system_tts")
    require(provider)
    voices = run(provider.voices())
    paths = run(provider.synthesize_lines([SpeechLine(text="Rented the whip and returned it by six"), SpeechLine(text="Fake it till the card declines")], tmp_path))
    assert voices and len(paths) == 2
    for path in paths:
        info = ffmpeg.probe(path)
        assert info.has_audio and 0.8 < info.duration < 15 and ffmpeg.mean_volume_db(path) > -45


def test_image_with_pollinations(tmp_path):
    from PIL import Image

    provider = build("image", "pollinations")
    require(provider)
    try:
        path = run(provider.generate_image(ImageRequest(prompt="cartoon llama rapper on a jet ski, album cover", width=512, height=512, seed=3), tmp_path / "img.png"))
    except TrollMusicError as exc:  # the keyless tier is often saturated
        pytest.skip(f"Pollinations refused the request: {exc.message}")
    assert min(Image.open(path).size) >= 256


def test_musicgen_generates_music(tmp_path):
    provider = build("music", "musicgen", model=os.environ.get("TROLL_TEST_MUSICGEN_MODEL"))
    require(provider)
    path = run(provider.generate_instrumental(BeatRequest(genre="lo-fi", bpm=90, duration_seconds=6), tmp_path / "gen", 1))
    info = ffmpeg.probe(path)
    assert info.has_audio and 4 < info.duration < 9 and ffmpeg.mean_volume_db(path) > -50


def test_acestep_sings_a_song(tmp_path):
    url = os.environ.get("TROLL_TEST_ACESTEP_URL")
    if not url:
        pytest.skip("TROLL_TEST_ACESTEP_URL is not set")
    provider = build("music", "acestep", base_url=url)
    require(provider)
    path = run(provider.generate_song(SongRequest(lyrics_text="[Verse 1]\nRented the whip and returned it by six", style_prompt="comedy trap, male rap vocal", duration_seconds=20), tmp_path / "song", 1))
    assert ffmpeg.probe(path).duration > 10


def test_elevenlabs_speech(tmp_path):
    key = os.environ.get("TROLL_TEST_ELEVENLABS_KEY")
    if not key:
        pytest.skip("TROLL_TEST_ELEVENLABS_KEY is not set")
    provider = build("voice", "elevenlabs", api_key=key)
    require(provider)
    voices = run(provider.voices())
    paths = run(provider.synthesize_lines([SpeechLine(text="Fake it till the card declines", voice=voices[0])], tmp_path))
    assert ffmpeg.probe(paths[0]).duration > 0.5
