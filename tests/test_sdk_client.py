"""The SDK's REST client, run against the real FastAPI app in-process."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.core import security
from backend.core.config import Settings
from backend.main import create_app
from tests.test_studio import LYRICS_TEXT, BrokenMusic, FakeVoice
from troll_music_ai import (
    ApiError,
    Asset,
    AsyncTrollMusicClient,
    AuthenticationError,
    JobFailedError,
    JobInfo,
    ProviderUnavailableError,
    TrollMusic,
    TrollMusicClient,
)
from troll_music_ai.providers import MockTextProvider


def connect(settings, api_key=None, **providers) -> AsyncTrollMusicClient:
    providers.setdefault("voice", FakeVoice())
    providers.setdefault("text", MockTextProvider())
    app = create_app(settings, providers=providers, inline_jobs=True)
    return AsyncTrollMusicClient(api_key, base_url="http://studio.test", transport=httpx.ASGITransport(app=app), poll_interval=0)


def test_full_pipeline_through_the_sdk(settings, tmp_path):
    async def run():
        async with connect(settings) as client:
            assert (await client.health())["status"] == "ok"
            project = await client.create_project("SDK album")
            lyrics = await client.generate_lyrics("my landlord", genre="drill", project=project)
            assert isinstance(lyrics, Asset) and lyrics.is_mock and lyrics.lyrics.sections
            assert lyrics.job.provider == "mock" and lyrics.project_id == project.id

            own = await client.import_lyrics("Layaway", LYRICS_TEXT, project=project)
            seen: list[float] = []
            beat = await client.generate_beat(genre="trap", bpm=120, duration_seconds=6, project=project, on_progress=lambda job: seen.append(job.progress))
            assert beat.kind == "beat" and beat.meta["bpm"] == 120 and not beat.is_ai and seen[-1] == 1.0

            song = await client.generate_song(own, beat, title="Layaway")
            assert song.kind == "song" and song.duration_seconds > beat.duration_seconds
            video = await client.generate_music_video(song, aspect="1:1", style="retro")
            assert video.mime_type == "video/mp4" and video.meta["renderer"] == "ffmpeg-stills"
            cover = await client.generate_artwork("Layaway", genre="trap")

            mp3 = await client.download(song, tmp_path / "out" / "song.mp3")
            mp4 = await client.download(video, tmp_path / "out" / "video.mp4")
            png = await client.download(cover, tmp_path / "out" / "cover.png")
            assert mp3.stat().st_size == song.size_bytes and mp4.read_bytes()[4:8] == b"ftyp" and png.read_bytes()[:4] == b"\x89PNG"

            kinds = {asset.kind for asset in await client.list_assets(project=project)}
            assert {"lyrics", "beat"} <= kinds
            states = {state.kind: state for state in await client.providers()}
            assert states["music"].provider == "procedural" and (await client.check_provider("music"))["ok"]

            queued = await client.generate_beat(duration_seconds=5, wait=False)
            assert isinstance(queued, JobInfo) and (await client.wait_for_job(queued)).status == "completed"

    asyncio.run(run())


def test_errors_are_typed(settings, tmp_path):
    async def run():
        async with connect(settings, music=BrokenMusic()) as client:
            with pytest.raises(JobFailedError) as failed:
                await client.generate_beat()
            assert failed.value.code == "provider_unavailable" and failed.value.job.status == "failed"
            assert (await client.retry_job(failed.value.job)).kind == "beat.generate"

            with pytest.raises(ApiError) as invalid:
                await client.generate_beat(bpm=999)
            assert invalid.value.status_code == 422 and invalid.value.code == "validation_error"
            with pytest.raises(ApiError) as missing:
                await client.get_asset("nope")
            assert missing.value.status_code == 404

            sample = tmp_path / "me.wav"
            from tests.test_studio import wav_bytes

            sample.write_bytes(wav_bytes(tmp_path, 8))
            with pytest.raises(ApiError) as consent:
                await client.create_voice_profile("Me", sample, owner_name="Sam Example", consent_statement="I allow this app to clone my voice.", consent_confirmed=False)
            assert consent.value.code == "consent_required"
            profile = await client.create_voice_profile("Me", sample, owner_name="Sam Example", consent_statement="I allow this app to clone my voice.", consent_confirmed=True)
            assert profile.usable is False and [p.id for p in await client.list_voice_profiles()] == [profile.id]
            await client.delete_voice_profile(profile)
            assert await client.list_voice_profiles() == []

    asyncio.run(run())


def test_api_key_is_sent_and_enforced(settings):
    locked = Settings(_env_file=None, database_url=settings.database_url, storage_dir=settings.storage_dir, api_key="let-me-in")

    async def run():
        async with connect(locked) as anonymous:
            with pytest.raises(AuthenticationError):
                await anonymous.list_projects()
        async with connect(locked, api_key="let-me-in") as client:
            assert await client.list_projects() == []

    try:
        asyncio.run(run())
    finally:
        security.configure(None)


def test_trollmusic_with_a_key_or_url_is_the_blocking_rest_client():
    client = TrollMusic(api_key="k", base_url="http://127.0.0.1:9")
    assert isinstance(client, TrollMusicClient) and client.base_url == "http://127.0.0.1:9"
    with client, pytest.raises(ProviderUnavailableError, match="Is it running"):
        client.health()
    assert not isinstance(TrollMusic(), TrollMusicClient)


def test_local_toolkit_writes_a_beat_without_a_server(tmp_path):
    path = TrollMusic().generate_beat(tmp_path / "beat.wav", genre="drill", bpm=140, duration_seconds=5)
    assert path.is_file() and path.stat().st_size > 100_000


def test_one_button_troll_through_the_sdk(settings):
    async def run():
        async with connect(settings) as client:
            idea = await client.random_troll()
            song = await client.troll(idea["situation"], kind="roast", style="country", target="Dave")
            assert song.kind == "song" and song.meta["troll"]["target"] == "Dave"
            assert len(song.job.result_asset_ids) == 5  # lyrics, vocals, beat, song, cover

    asyncio.run(run())
