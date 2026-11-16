"""Beats, uploads, vocals, songs, videos, artwork, voices, jobs, settings, auth.

These run the real pipeline (procedural synth, FFmpeg, Pillow) and produce real
files. Only the voice provider is a fake, so the suite does not depend on an
operating-system speech engine. Nothing here proves an AI model works: see
``tests/integration`` for that.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from backend.models.tables import Job
from tests.conftest import ScriptedProvider
from troll_music_ai import ProviderUnavailableError
from troll_music_ai.providers import (
    MockTextProvider,
    MusicCapabilities,
    MusicGenerationProvider,
    ProviderInfo,
    ProviderKind,
    ProviderStatus,
    VoiceCapabilities,
    VoiceProvider,
)
from troll_music_ai.providers.procedural import SR, write_wav

LYRICS_TEXT = """[Verse 1]
Rented the whip and returned it by six
Crypto guru still lives with his mum

[Chorus]
Fake it till the card declines
"""
CONSENT = {
    "name": "My voice",
    "owner_name": "Sam Example",
    "consent_statement": "I am Sam Example and I allow this app to clone my voice.",
    "consent_confirmed": "true",
}


def tone(seconds: float, freq: float = 220.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def wav_bytes(tmp_path: Path, seconds: float) -> bytes:
    path = tmp_path / f"tone_{seconds}.wav"
    write_wav(path, tone(seconds))
    return path.read_bytes()


class FakeVoice(VoiceProvider):
    """Writes a short tone per line. Optionally pretends to clone."""

    def __init__(self, cloning: bool = False) -> None:
        self._cloning = cloning
        self.spoken: list = []
        self.deleted: list[str] = []

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="fake_voice", kind=ProviderKind.VOICE, model="fake-1", is_mock=True, is_ai=False)

    @property
    def capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities(cloning=self._cloning, conversion=self._cloning)

    async def check(self) -> ProviderStatus:
        return ProviderStatus(ok=True, detail="fake")

    async def voices(self) -> list[str]:
        return ["Ada", "Bob"]

    async def synthesize_lines(self, lines, out_dir):
        self.spoken += lines
        paths = []
        for index, line in enumerate(lines):
            path = out_dir / f"{index:03d}.wav"
            write_wav(path, tone(0.9, 200 + 20 * index))
            paths.append(path)
        return paths

    async def create_voice(self, name, sample_path):
        return f"cloned:{name}"

    async def delete_voice(self, provider_voice_id):
        self.deleted.append(provider_voice_id)

    async def convert_voice(self, source_path, provider_voice_id, out_path):
        target = out_path.with_suffix(".wav")
        write_wav(target, tone(2.0, 330))
        return target


class BrokenMusic(MusicGenerationProvider):
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="broken", kind=ProviderKind.MUSIC, model="x")

    @property
    def capabilities(self) -> MusicCapabilities:
        return MusicCapabilities()

    async def check(self) -> ProviderStatus:
        return ProviderStatus(ok=False, detail="down")

    async def generate_instrumental(self, request, out_path, seed):
        raise ProviderUnavailableError("The music server is not reachable.")


@pytest.fixture
def studio(settings):
    """Client factory with the fake voice; other providers are the built-ins."""
    clients = []

    def _make(**providers) -> TestClient:
        providers.setdefault("voice", FakeVoice())
        providers.setdefault("text", MockTextProvider())
        client = TestClient(create_app(settings, providers=providers, inline_jobs=True))
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


def done(client: TestClient, response) -> dict:
    assert response.status_code == 202, response.text
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "completed", job
    return job


def asset_of(client: TestClient, job: dict) -> dict:
    return client.get(f"/api/assets/{job['result_asset_id']}").json()


def import_lyrics(client: TestClient) -> dict:
    response = client.post("/api/lyrics/import", json={"title": "Layaway", "text": LYRICS_TEXT})
    assert response.status_code == 201, response.text
    return response.json()


def make_beat(client: TestClient, **request) -> dict:
    body = {"request": {"genre": "trap", "bpm": 120, "duration_seconds": 6, **request}}
    return asset_of(client, done(client, client.post("/api/beats/generate", json=body)))


# ---------------------------------- beats ---------------------------------- #


def test_beat_generation_writes_a_real_mp3_with_the_requested_tempo_and_length(studio):
    client = studio()
    job = done(client, client.post("/api/beats/generate", json={"request": {"genre": "drill", "bpm": 140, "duration_seconds": 6, "variations": 2}}))
    assert job["provider"] == "procedural" and len(job["result_asset_ids"]) == 2
    beat = asset_of(client, job)
    assert beat["kind"] == "beat" and beat["has_file"] and beat["mime_type"] == "audio/mpeg"
    assert beat["is_ai"] is False and beat["is_mock"] is False  # built-in engine, honestly labelled
    assert beat["meta"]["bpm"] == 140 and beat["meta"]["bpm_exact"] is True
    assert abs(beat["duration_seconds"] - 6) < 0.3 and beat["size_bytes"] > 20_000

    file = client.get(f"/api/assets/{beat['id']}/file")
    assert file.status_code == 200 and file.headers["content-type"] == "audio/mpeg"
    assert len(file.content) == beat["size_bytes"]
    ranged = client.get(f"/api/assets/{beat['id']}/file", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206 and len(ranged.content) == 100
    download = client.get(f"/api/assets/{beat['id']}/file?download=1")
    assert download.headers["content-disposition"].startswith("attachment")


def test_two_variations_are_different_audio(studio):
    client = studio()
    job = done(client, client.post("/api/beats/generate", json={"request": {"bpm": 100, "duration_seconds": 5, "variations": 2}}))
    first, second = (client.get(f"/api/assets/{i}/file").content for i in job["result_asset_ids"])
    assert first != second


def test_beat_validation_and_missing_provider(studio):
    client = studio()
    assert client.post("/api/beats/generate", json={"request": {"bpm": 999}}).status_code == 422
    bare = studio(music=None)
    response = bare.post("/api/beats/generate", json={"request": {}})
    assert response.status_code == 503 and response.json()["error"]["code"] == "provider_not_configured"
    assert bare.get("/api/jobs").json() == []


def test_a_failing_music_provider_fails_the_job_with_a_readable_error(studio):
    client = studio(music=BrokenMusic())
    job = client.get(f"/api/jobs/{client.post('/api/beats/generate', json={'request': {}}).json()['id']}").json()
    assert job["status"] == "failed" and job["error_code"] == "provider_unavailable"
    assert "not reachable" in job["error"] and client.get("/api/assets").json() == []


# --------------------------------- uploads --------------------------------- #


def test_upload_accepts_audio_and_rejects_everything_else(studio, tmp_path):
    client = studio()
    ok = client.post("/api/assets/upload", files={"file": ("my beat.wav", wav_bytes(tmp_path, 3), "audio/wav")}, data={"kind": "beat", "bpm": "95"})
    assert ok.status_code == 201, ok.text
    asset = ok.json()
    assert asset["origin"] == "uploaded" and asset["title"] == "my beat" and asset["is_ai"] is False
    assert asset["mime_type"] == "audio/mpeg" and abs(asset["duration_seconds"] - 3) < 0.3 and asset["meta"]["bpm"] == 95

    fake = client.post("/api/assets/upload", files={"file": ("virus.mp3", b"this is not audio at all", "audio/mpeg")})
    assert fake.status_code == 422 and fake.json()["error"]["code"] == "invalid_media"
    empty = client.post("/api/assets/upload", files={"file": ("empty.wav", b"", "audio/wav")})
    assert empty.status_code == 422
    assert client.post("/api/assets/upload", files={"file": ("a.wav", wav_bytes(tmp_path, 2), "audio/wav")}, data={"kind": "video"}).status_code == 422


def test_upload_size_limit(settings, tmp_path):
    small = Settings(_env_file=None, database_url=settings.database_url, storage_dir=settings.storage_dir, max_upload_mb=0)
    with TestClient(create_app(small, inline_jobs=True)) as client:
        response = client.post("/api/assets/upload", files={"file": ("a.wav", wav_bytes(tmp_path, 2), "audio/wav")})
        assert response.status_code == 413


def test_lyrics_import_needs_no_model(studio):
    client = studio(text=None)
    lyrics = import_lyrics(client)
    assert lyrics["origin"] == "imported" and lyrics["is_ai"] is False and lyrics["provider"] is None
    assert [s["label"] for s in lyrics["content"]["sections"]] == ["Verse 1", "Chorus"]
    assert client.post("/api/lyrics/import", json={"title": "x", "text": "   \n  \n "}).status_code == 422


# ------------------------------ vocals and songs ---------------------------- #


def test_vocals_are_placed_on_the_beat_grid_and_labelled_as_spoken(studio):
    client = studio()
    lyrics = import_lyrics(client)
    vocals = asset_of(client, done(client, client.post("/api/vocals/generate", json={"lyrics_asset_id": lyrics["id"], "bpm": 120, "voice": "Ada"})))
    assert vocals["kind"] == "vocals" and vocals["has_file"] and vocals["meta"]["delivery"] == "spoken"
    timings = vocals["meta"]["line_timings"]
    assert [t["text"] for t in timings] == [line for s in lyrics["content"]["sections"] for line in s["lines"]]
    bar = 240 / 120
    assert all(abs(t["start"] / bar - round(t["start"] / bar)) < 1e-6 for t in timings)  # every line starts on a bar
    assert timings[0]["start"] == 2 * bar  # two bars of lead-in
    assert all(a["end"] <= b["start"] for a, b in zip(timings, timings[1:]))
    sources = client.get(f"/api/assets/{vocals['id']}/sources").json()
    assert [(s["relation"], s["asset"]["id"]) for s in sources] == [("lyrics", lyrics["id"])]


def test_song_mixes_existing_parts_without_regenerating_them(studio):
    voice = FakeVoice()
    client = studio(voice=voice)
    lyrics, beat = import_lyrics(client), make_beat(client)
    beat_bytes = client.get(f"/api/assets/{beat['id']}/file").content

    job = done(client, client.post("/api/songs/generate", json={"lyrics_asset_id": lyrics["id"], "beat_asset_id": beat["id"], "title": "Layaway (final)"}))
    song = asset_of(client, job)
    assert song["kind"] == "song" and song["title"] == "Layaway (final)" and song["mime_type"] == "audio/mpeg"
    assert len(job["result_asset_ids"]) == 2  # the vocal track is its own asset
    relations = {s["relation"]: s["asset"] for s in client.get(f"/api/assets/{song['id']}/sources").json()}
    assert set(relations) == {"lyrics", "beat", "vocals"} and relations["beat"]["id"] == beat["id"]
    vocals = relations["vocals"]
    assert song["duration_seconds"] >= vocals["duration_seconds"] and song["meta"]["line_timings"]
    # The beat is longer than its 6 s source because it was looped under the vocal.
    assert song["duration_seconds"] > beat["duration_seconds"]
    assert client.get(f"/api/assets/{beat['id']}/file").content == beat_bytes  # source untouched

    # Mixing again with the existing vocal track does not call the voice provider.
    calls = len(voice.spoken)
    remix = done(client, client.post("/api/songs/generate", json={
        "lyrics_asset_id": lyrics["id"], "beat_asset_id": beat["id"], "vocals_asset_id": vocals["id"], "vocal_gain_db": 6,
    }))
    assert len(voice.spoken) == calls and remix["result_asset_ids"] == [remix["result_asset_id"]]


def test_song_requests_are_validated_before_a_job_is_created(studio):
    client = studio()
    lyrics = import_lyrics(client)
    assert client.post("/api/songs/generate", json={"lyrics_asset_id": lyrics["id"]}).status_code == 422
    assert client.post("/api/songs/generate", json={"lyrics_asset_id": lyrics["id"], "beat_asset_id": "nope"}).status_code == 404
    # The built-in beat engine cannot sing, and says so instead of faking it.
    sung = client.post("/api/songs/generate", json={"lyrics_asset_id": lyrics["id"], "mode": "model"})
    assert sung.status_code == 501 and "cannot sing" in sung.json()["error"]["message"]
    assert client.get("/api/jobs").json() == []


# ----------------------------- video and artwork --------------------------- #


def test_video_from_a_song_is_a_real_mp4_with_synced_scenes(studio):
    client = studio()
    lyrics, beat = import_lyrics(client), make_beat(client)
    song = asset_of(client, done(client, client.post("/api/songs/generate", json={"lyrics_asset_id": lyrics["id"], "beat_asset_id": beat["id"]})))
    job = done(client, client.post("/api/videos/generate", json={"audio_asset_id": song["id"], "aspect": "9:16", "style": "meme"}))
    video = asset_of(client, job)
    assert video["kind"] == "video" and video["mime_type"] == "video/mp4"
    assert (video["meta"]["width"], video["meta"]["height"]) == (720, 1280)
    assert abs(video["duration_seconds"] - song["duration_seconds"]) < 0.5
    assert video["meta"]["renderer"] == "ffmpeg-stills" and video["meta"]["subtitles"] is True
    assert video["is_ai"] is False and video["meta"]["image_provider"] == "typographic"
    content = client.get(f"/api/assets/{video['id']}/file").content
    assert content[4:8] == b"ftyp" and len(content) == video["size_bytes"]

    storyboard = client.get(f"/api/assets/{video['meta']['storyboard_asset_id']}").json()
    scenes = storyboard["content"]["scenes"]
    assert storyboard["kind"] == "storyboard" and storyboard["content"]["source"] == "template"
    assert scenes[0]["start"] == 0 and abs(scenes[-1]["end"] - song["duration_seconds"]) < 0.5
    assert all(a["end"] == b["start"] for a, b in zip(scenes, scenes[1:]))
    # The second section's scene starts exactly where its first line is performed.
    chorus_start = next(t["start"] for t in song["meta"]["line_timings"] if t["label"] == "Chorus")
    assert any(abs(s["start"] - chorus_start) < 0.01 for s in scenes)


def test_video_from_lyrics_alone_and_validation(studio):
    client = studio()
    lyrics = import_lyrics(client)
    video = asset_of(client, done(client, client.post("/api/videos/generate", json={"lyrics_asset_id": lyrics["id"], "duration_seconds": 4, "aspect": "1:1"})))
    assert video["meta"]["has_audio"] is False and abs(video["duration_seconds"] - 4) < 0.3
    assert client.post("/api/videos/generate", json={}).status_code == 422


def test_storyboard_uses_the_text_model_when_one_is_configured(studio):
    scenes = {"scenes": [{"description": f"shot {i}", "image_prompt": f"a llama in scene {i}"} for i in range(2)]}
    client = studio(text=ScriptedProvider(scenes))
    lyrics = import_lyrics(client)
    video = asset_of(client, done(client, client.post("/api/videos/generate", json={"lyrics_asset_id": lyrics["id"], "duration_seconds": 6})))
    storyboard = client.get(f"/api/assets/{video['meta']['storyboard_asset_id']}").json()
    assert storyboard["content"]["source"] == "llm" and storyboard["provider"] == "scripted"
    assert "llama" in storyboard["content"]["scenes"][0]["image_prompt"]


def test_artwork_is_a_1024_square_png(studio):
    from PIL import Image

    client = studio()
    art = asset_of(client, done(client, client.post("/api/artwork/generate", json={"title": "Layaway", "genre": "drill", "style": "retro"})))
    assert art["kind"] == "artwork" and art["mime_type"] == "image/png" and art["is_ai"] is False
    image = Image.open(io.BytesIO(client.get(f"/api/assets/{art['id']}/file").content))
    assert image.size == (1024, 1024) and image.format == "PNG"


# ------------------------------ voice profiles ----------------------------- #


def test_a_voice_profile_cannot_be_created_without_consent(studio, tmp_path):
    client = studio()
    sample = {"file": ("me.wav", wav_bytes(tmp_path, 8), "audio/wav")}
    for missing in ({"consent_confirmed": "false"}, {"owner_name": ""}, {"consent_statement": "ok"}):
        response = client.post("/api/voices", files=sample, data={**CONSENT, **missing})
        assert response.status_code == 422 and response.json()["error"]["code"] == "consent_required"
    assert client.get("/api/voices").json() == []
    assert not list(Path(client.app.state.settings.storage_dir).glob("voices/*"))


def test_voice_sample_is_validated(studio, tmp_path):
    client = studio()
    short = client.post("/api/voices", files={"file": ("me.wav", wav_bytes(tmp_path, 2), "audio/wav")}, data=CONSENT)
    assert short.status_code == 422 and "between" in short.json()["error"]["message"]
    junk = client.post("/api/voices", files={"file": ("me.wav", b"not audio", "audio/wav")}, data=CONSENT)
    assert junk.status_code == 422 and junk.json()["error"]["code"] == "invalid_media"


def test_a_profile_is_not_usable_with_a_provider_that_cannot_clone(studio, tmp_path):
    client = studio()
    profile = client.post("/api/voices", files={"file": ("me.wav", wav_bytes(tmp_path, 8), "audio/wav")}, data=CONSENT)
    assert profile.status_code == 201, profile.text
    body = profile.json()
    assert body["usable"] is False and body["provider"] is None and body["owner_name"] == "Sam Example"
    assert "provider_voice_id" not in body and "sample_storage_key" not in body
    lyrics = import_lyrics(client)
    refused = client.post("/api/vocals/generate", json={"lyrics_asset_id": lyrics["id"], "voice_profile_id": body["id"]})
    assert refused.status_code == 501 and "cannot use voice profiles" in refused.json()["error"]["message"]


def test_cloned_voice_end_to_end_and_deletion_removes_everything(studio, tmp_path):
    voice = FakeVoice(cloning=True)
    client = studio(voice=voice)
    profile = client.post("/api/voices", files={"file": ("me.wav", wav_bytes(tmp_path, 8), "audio/wav")}, data=CONSENT).json()
    assert profile["usable"] is True and profile["provider"] == "fake_voice"
    assert client.get(f"/api/voices/{profile['id']}/sample").headers["content-type"] == "audio/wav"

    lyrics = import_lyrics(client)
    vocals = asset_of(client, done(client, client.post("/api/vocals/generate", json={"lyrics_asset_id": lyrics["id"], "voice_profile_id": profile["id"]})))
    assert vocals["meta"]["voice"] == "My voice" and voice.spoken[0].voice == "cloned:My voice"
    converted = asset_of(client, done(client, client.post("/api/vocals/convert", json={"source_asset_id": vocals["id"], "voice_profile_id": profile["id"]})))
    assert converted["origin"] == "converted" and converted["kind"] == "vocals"

    sample = Path(client.app.state.settings.storage_dir) / "voices" / f"{profile['id']}.wav"
    assert sample.is_file()
    assert client.delete(f"/api/voices/{profile['id']}").json()["deleted"] is True
    assert not sample.exists() and voice.deleted == ["cloned:My voice"] and client.get("/api/voices").json() == []
    assert client.get(f"/api/voices/{profile['id']}/sample").status_code == 404


def test_stock_voices_say_the_provider_does_not_sing(studio):
    stock = studio().get("/api/voices/stock").json()
    assert stock["voices"] == ["Ada", "Bob"] and stock["singing"] is False and "does not sing" in stock["note"]


# --------------------------------- battles --------------------------------- #

BATTLE = {
    "topic": "who makes the better sandwich",
    "character_a": {"name": "DJ Crumb", "personality": "smug baker"},
    "character_b": {"name": "MC Mayo", "personality": "chaotic condiment"},
    "rounds": 1,
}


def test_battle_lyrics_alternate_performers_and_get_two_voices(studio):
    voice = FakeVoice()
    client = studio(voice=voice)
    battle = asset_of(client, done(client, client.post("/api/battles/generate", json={"request": BATTLE})))
    assert battle["kind"] == "lyrics" and battle["origin"] == "battle" and battle["is_mock"] is True
    performers = [s["performer"] for s in battle["content"]["sections"] if s["performer"]]
    assert set(performers) == {"DJ Crumb", "MC Mayo"}

    done(client, client.post("/api/vocals/generate", json={"lyrics_asset_id": battle["id"], "voice": "Ada", "voice_b": "Bob"}))
    assert {line.voice for line in voice.spoken} == {"Ada", "Bob"}
    suggestions = client.post("/api/battles/characters", json={"topic": BATTLE["topic"]}).json()
    assert len(suggestions["characters"]) >= 2 and suggestions["is_mock"] is True


# ----------------------------------- jobs ---------------------------------- #


def test_cancel_and_retry(studio):
    client = studio(music=BrokenMusic())
    failed = client.post("/api/beats/generate", json={"request": {"genre": "phonk"}}).json()
    assert client.post(f"/api/jobs/{failed['id']}/cancel").status_code == 409

    retried = client.post(f"/api/jobs/{failed['id']}/retry")
    assert retried.status_code == 202
    again = client.get(f"/api/jobs/{retried.json()['id']}").json()
    assert again["retry_of"] == failed["id"] and again["kind"] == "beat.generate" and again["status"] == "failed"

    with client.app.state.session_factory() as session:
        queued = Job(kind="beat.generate", params={"request": {}})
        session.add(queued)
        session.commit()
        queued_id = queued.id
    assert [j["id"] for j in client.get("/api/jobs?active=true").json()] == [queued_id]
    cancelled = client.post(f"/api/jobs/{queued_id}/cancel").json()
    assert cancelled["status"] == "cancelled" and cancelled["finished_at"]
    client.app.state.job_queue.enqueue(queued_id)  # a cancelled job never runs
    assert client.get(f"/api/jobs/{queued_id}").json()["status"] == "cancelled"
    assert client.post(f"/api/jobs/{failed['id']}/retry").status_code == 202
    assert client.post("/api/jobs/missing/retry").status_code == 404


def test_cancelling_a_running_job_stops_it_at_the_next_step(studio):
    client = studio()

    class CancelsItself(BrokenMusic):
        async def generate_instrumental(self, request, out_path, seed):
            with client.app.state.session_factory() as session:
                job = session.query(Job).one()
                job.cancel_requested = True
                session.commit()
            from troll_music_ai.providers.procedural import ProceduralBeatProvider

            return await ProceduralBeatProvider().generate_instrumental(request, out_path, seed)

    client.app.state.providers._overrides["music"] = CancelsItself()
    job = client.get(f"/api/jobs/{client.post('/api/beats/generate', json={'request': {'duration_seconds': 5}}).json()['id']}").json()
    assert job["status"] == "cancelled" and client.get("/api/assets").json() == []


# -------------------------- deleting and duplicating ------------------------ #


def test_deleting_assets_and_projects_removes_their_files(studio):
    client = studio()
    root = Path(client.app.state.settings.storage_dir)
    project = client.post("/api/projects", json={"name": "Album"}).json()
    body = {"project_id": project["id"], "request": {"duration_seconds": 5}}
    beat = asset_of(client, done(client, client.post("/api/beats/generate", json=body)))
    loose = make_beat(client)
    assert len(list(root.glob("beat/*.mp3"))) == 2

    copy = client.post(f"/api/projects/{project['id']}/duplicate").json()
    copied = client.get(f"/api/projects/{copy['id']}/assets").json()[0]
    assert copied["id"] != beat["id"] and client.get(f"/api/assets/{copied['id']}/file").status_code == 200

    bundle = zipfile.ZipFile(io.BytesIO(client.get(f"/api/projects/{project['id']}/export").content))
    assert any(name.startswith("beat/") and name.endswith(".mp3") for name in bundle.namelist())

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/assets/{copied['id']}/file").status_code == 200  # the copy owns its file
    assert client.delete(f"/api/assets/{loose['id']}").status_code == 204
    assert [p.stem for p in root.glob("beat/*.mp3")] == [copied["id"]]


# ------------------------------ model settings ----------------------------- #


def test_model_settings_switch_providers_without_exposing_keys(settings):
    with TestClient(create_app(settings, providers={"voice": FakeVoice()}, inline_jobs=True)) as client:
        states = {s["kind"]: s for s in client.get("/api/system/providers").json()}
        assert states["text"]["configured"] is False and states["text"]["source"] == "environment"
        assert states["music"]["provider"] == "procedural" and states["voice"]["source"] == "override"
        names = {o["name"] for o in states["music"]["options"]}
        assert {"procedural", "musicgen", "acestep", "elevenlabs_music"} <= names
        assert client.post("/api/lyrics/generate", json={"request": {"prompt": "my landlord"}}).status_code == 503

        # A provider that cannot work as configured is rejected, not saved.
        rejected = client.put("/api/system/providers/text", json={"provider": "openai", "model": "gpt-x"})
        assert rejected.status_code == 422 and "API_KEY" in rejected.json()["error"]["message"]
        assert client.put("/api/system/providers/text", json={"provider": "nope"}).status_code == 422
        assert client.put("/api/system/providers/smell", json={"provider": "mock"}).status_code == 404

        saved = client.put("/api/system/providers/text", json={
            "provider": "openai_compatible", "base_url": "http://llm.test/v1", "model": "tiny", "api_key": "sk-top-secret",
        })
        assert saved.status_code == 200 and "sk-top-secret" not in saved.text
        state = saved.json()
        assert state["source"] == "settings" and state["has_api_key"] is True and state["model"] == "tiny"
        assert "sk-top-secret" not in client.get("/api/system/providers").text
        # Omitting the key keeps it; switching provider drops it.
        assert client.put("/api/system/providers/text", json={"provider": "openai_compatible", "base_url": "http://llm.test/v1", "model": "other"}).json()["has_api_key"] is True

        switched = client.put("/api/system/providers/text", json={"provider": "mock"}).json()
        assert switched["is_mock"] is True and switched["has_api_key"] is False
        job = client.post("/api/lyrics/generate", json={"request": {"prompt": "my landlord"}})
        assert client.get(f"/api/jobs/{job.json()['id']}").json()["provider"] == "mock"
        assert client.post("/api/system/providers/text/check").json()["ok"] is True

        disabled = client.put("/api/system/providers/music", json={"provider": "procedural", "enabled": False}).json()
        assert disabled["configured"] is False and disabled["enabled"] is False
        assert client.post("/api/beats/generate", json={"request": {}}).status_code == 503
        assert client.delete("/api/system/providers/music").json()["configured"] is True
        assert client.delete("/api/system/providers/text").json()["configured"] is False


def test_hardware_and_options(studio):
    client = studio()
    hardware = client.get("/api/system/hardware").json()
    assert hardware["ffmpeg"]["ok"] is True and "torch" in hardware["packages"] and isinstance(hardware["gpus"], list)
    options = client.get("/api/meta/options").json()
    assert "16:9" in options["aspects"] and options["instruments"] and options["visual_styles"]


# ----------------------------------- auth ---------------------------------- #


def test_api_key_protects_everything_but_health(settings):
    from backend.core import security

    locked = Settings(_env_file=None, database_url=settings.database_url, storage_dir=settings.storage_dir, api_key="let-me-in")
    try:
        with TestClient(create_app(locked, inline_jobs=True)) as client:
            assert client.get("/api/health").json() == {"status": "ok", "auth_required": True}
            for path in ("/api/projects", "/api/assets", "/api/system/providers", "/api/voices", "/api/jobs"):
                denied = client.get(path)
                assert denied.status_code == 401 and denied.json()["error"]["code"] == "unauthorized"
            assert client.get("/api/projects", headers={"Authorization": "Bearer wrong"}).status_code == 401

            auth = {"Authorization": "Bearer let-me-in"}
            job = client.post("/api/beats/generate", json={"request": {"duration_seconds": 5}}, headers=auth).json()
            first = client.get(f"/api/assets/{job['result_asset_ids'][0] if job['result_asset_ids'] else client.get('/api/jobs/' + job['id'], headers=auth).json()['result_asset_id']}", headers=auth).json()
            other = client.post("/api/beats/generate", json={"request": {"duration_seconds": 5}}, headers=auth).json()
            other_id = client.get(f"/api/jobs/{other['id']}", headers=auth).json()["result_asset_id"]

            # A media element can use the signed token, but only for that one file.
            url = f"/api/assets/{first['id']}/file"
            assert client.get(url).status_code == 401
            assert client.get(f"{url}?token={first['file_token']}").status_code == 200
            assert client.get(f"/api/assets/{other_id}/file?token={first['file_token']}").status_code == 401
            assert client.get(f"/api/assets/{first['id']}?token={first['file_token']}").status_code == 401
            assert "let-me-in" not in first["file_token"]
    finally:
        security.configure(None)
