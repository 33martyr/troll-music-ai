"""Full songs with AI-sung vocals: adapters with the network mocked, and the
troll pipeline with a fake singing provider.

Nothing here calls ElevenLabs or ACE-Step. Passing proves the requests we send
and how we handle the answers; it does not prove a real model sings well.
"""

from __future__ import annotations

import asyncio
import json
import math
import struct
import wave

import httpx
import pytest

from tests.test_studio import FakeVoice, studio  # noqa: F401  (fixture)
from tests.test_troll import outputs, troll
from troll_music_ai import ProviderNotConfiguredError, ProviderResponseError, ProviderUnavailableError, TrollRequest
from troll_music_ai.providers import MusicCapabilities, MusicGenerationProvider, ProviderInfo, ProviderKind, ProviderStatus
from troll_music_ai.providers.music_models import AceStepProvider, ElevenLabsMusicProvider, plan_sections
from troll_music_ai.types import SongPart, SongRequest

DAVE = "My friend Dave thinks he's rich but borrows money every Friday"
PARTS = [
    SongPart(label="Intro", lines=["Yeah", "Dave on the mic"]),
    SongPart(label="Verse 1", lines=[f"bar {i}" for i in range(8)]),
    SongPart(label="Chorus", lines=["Borrow, borrow", "Every Friday", "Borrow, borrow", "Pay me back"]),
    SongPart(label="Outro", lines=["Declined"]),
]


def song(**extra) -> SongRequest:
    text = "\n\n".join("\n".join([f"[{p.label}]", *p.lines]) for p in PARTS)
    return SongRequest(lyrics_text=text, sections=PARTS, style_prompt="UK drill, 808s, aggressive rap vocals", duration_seconds=60, **extra)


def run(coro):
    return asyncio.run(coro)


def eleven(handler, model="music_v2_5", **kwargs) -> ElevenLabsMusicProvider:
    async def no_wait(_seconds):
        return None

    return ElevenLabsMusicProvider(
        base_url="https://api.elevenlabs.io", api_key="secret-key", model=model,
        transport=httpx.MockTransport(handler), sleep=no_wait, **kwargs,
    )


# ------------------------------- planning ---------------------------------- #


def test_sections_share_the_duration_by_how_much_they_sing():
    plan = plan_sections(song())
    assert [label for label, _, _ in plan] == ["Intro", "Verse 1", "Chorus", "Outro"]
    durations = {label: ms for label, _, ms in plan}
    assert durations["Verse 1"] > durations["Chorus"] > durations["Intro"]
    assert all(3000 <= ms <= 120_000 for ms in durations.values())
    assert abs(sum(durations.values()) - 60_000) < 6000  # minimums can add a little


def test_lines_are_clipped_to_the_hosted_limits():
    long = SongRequest(lyrics_text="x", style_prompt="pop", sections=[SongPart(label="Verse", lines=["y" * 300] * 40)])
    ((_, lines, _),) = plan_sections(long)
    assert len(lines) == 30 and all(len(line) == 200 for line in lines)


# ------------------------------ ElevenLabs --------------------------------- #


def test_elevenlabs_v2_sends_the_exact_lyrics_as_chunks(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"], seen["key"], seen["query"] = json.loads(request.content), request.headers["xi-api-key"], request.url.params
        return httpx.Response(200, content=b"ID3sung-song", headers={"content-type": "audio/mpeg"})

    provider = eleven(handler)
    assert provider.capabilities.with_vocals is True
    path = run(provider.generate_song(song(negative_style="spoken word"), tmp_path / "song", 7))
    assert path.suffix == ".mp3" and path.read_bytes() == b"ID3sung-song"
    body = seen["body"]
    assert body["model_id"] == "music_v2_5" and "prompt" not in body and seen["key"] == "secret-key"
    chunks = body["composition_plan"]["chunks"]
    assert [c["text"].splitlines()[0] for c in chunks] == ["[Intro]", "[Verse 1]", "[Chorus]", "[Outro]"]
    assert chunks[1]["text"].splitlines()[1:] == [f"bar {i}" for i in range(8)]  # every line, in order
    assert "UK drill" in chunks[0]["positive_styles"] and "great production quality" in chunks[0]["positive_styles"]
    assert "catchy hook" in chunks[2]["positive_styles"] and chunks[0]["negative_styles"] == ["spoken word"]
    assert seen["query"]["output_format"] == "mp3_44100_128"


def test_elevenlabs_v1_uses_the_sections_plan(tmp_path):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=b"ID3", headers={"content-type": "audio/mpeg"})

    run(eleven(handler, model="music_v1").generate_song(song(), tmp_path / "s", 1))
    plan = seen["body"]["composition_plan"]
    assert plan["positive_global_styles"][:2] == ["UK drill", "808s"]
    assert [s["section_name"] for s in plan["sections"]] == ["Intro", "Verse 1", "Chorus", "Outro"]
    assert plan["sections"][2]["lines"][0] == "Borrow, borrow" and seen["body"]["respect_sections_durations"] is False


def test_elevenlabs_retries_rate_limits_then_succeeds(tmp_path):
    answers = [
        httpx.Response(429, json={"detail": {"message": "busy"}}),
        httpx.Response(503, text="down"),
        httpx.Response(200, content=b"ID3ok", headers={"content-type": "audio/mpeg"}),
    ]
    calls = []

    def handler(request):
        calls.append(1)
        return answers.pop(0)

    path = run(eleven(handler).generate_song(song(), tmp_path / "s", 1))
    assert path.read_bytes() == b"ID3ok" and len(calls) == 3


def test_elevenlabs_gives_up_after_its_retries(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"detail": {"message": "too many requests"}})

    with pytest.raises(ProviderResponseError, match="429"):
        run(eleven(handler, retries=1).generate_song(song(), tmp_path / "s", 1))
    assert len(calls) == 2


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}, "rejected the API key"),
        (402, {"detail": {"message": "Payment required"}}, "needs a paid plan"),
        (403, {"detail": {"message": "Music is not available on the free plan"}}, "needs a paid plan"),
    ],
)
def test_elevenlabs_account_problems_are_explained_and_not_retried(tmp_path, status, body, expected):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, json=body)

    with pytest.raises(ProviderNotConfiguredError) as error:
        run(eleven(handler).generate_song(song(), tmp_path / "s", 1))
    assert expected in error.value.message and "secret-key" not in error.value.message and len(calls) == 1


def test_elevenlabs_bad_request_and_non_audio_answers_fail_clearly(tmp_path):
    invalid = eleven(lambda r: httpx.Response(422, json={"detail": [{"msg": "lines too long"}]}))
    with pytest.raises(ProviderResponseError, match="422"):
        run(invalid.generate_song(song(), tmp_path / "s", 1))
    not_audio = eleven(lambda r: httpx.Response(200, json={"status": "queued"}))
    with pytest.raises(ProviderResponseError, match="without audio"):
        run(not_audio.generate_song(song(), tmp_path / "s", 1))


def test_elevenlabs_timeout_is_not_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ProviderUnavailableError, match="timed out"):
        run(eleven(handler).generate_song(song(), tmp_path / "s", 1))
    assert len(calls) == 1  # a timed-out request may still have been charged


# -------------------------------- ACE-Step --------------------------------- #


def test_acestep_song_asks_the_planner_and_reports_failures(tmp_path):
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/release_task":
            bodies.append(json.loads(request.content))
            return httpx.Response(200, json={"code": 200, "data": {"task_id": "t1"}})
        return httpx.Response(200, json={"code": 200, "data": [{"task_id": "t1", "status": 2, "error": "CUDA out of memory"}]})

    provider = AceStepProvider(base_url="http://ace.test", poll_seconds=0, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderResponseError, match="CUDA out of memory"):
        run(provider.generate_song(song(), tmp_path / "s", 1))
    assert bodies[0]["thinking"] is True and "[Verse 1]" in bodies[0]["lyrics"] and bodies[0]["seed"] == 1


def test_acestep_gives_up_after_its_timeout(tmp_path):
    def handler(request):
        if request.url.path == "/release_task":
            return httpx.Response(200, json={"code": 200, "data": {"task_id": "t1"}})
        return httpx.Response(200, json={"code": 200, "data": [{"task_id": "t1", "status": 0}]})

    provider = AceStepProvider(base_url="http://ace.test", poll_seconds=0.01, timeout=0.03, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderUnavailableError, match="did not finish"):
        run(provider.generate_song(song(), tmp_path / "s", 1))


# ----------------------------- the troll job ------------------------------- #


def tone(path, seconds=6.0, rate=22050):
    """A real, playable WAV: a 220 Hz tone standing in for a sung song."""
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / rate))) for i in range(int(seconds * rate)))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)
    return path


class FakeSinger(MusicGenerationProvider):
    """Stands in for a music model that sings. Records what it was asked."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.fail, self.songs, self.beats = fail, [], 0

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="fake_singer", kind=ProviderKind.MUSIC, model="singer-1")

    @property
    def capabilities(self) -> MusicCapabilities:
        return MusicCapabilities(with_vocals=True, max_duration_seconds=300)

    async def check(self) -> ProviderStatus:
        return ProviderStatus(ok=True, detail="ok")

    async def generate_instrumental(self, request, out_path, seed):
        self.beats += 1
        return tone(out_path.with_suffix(".wav"), request.duration_seconds)

    async def generate_song(self, request, out_path, seed):
        self.songs.append(request)
        if self.fail:
            raise self.fail
        return tone(out_path.with_suffix(".wav"))


def test_a_singing_model_performs_the_whole_song(studio):  # noqa: F811
    singer, voice = FakeSinger(), FakeVoice()
    client = studio(music=singer, voice=voice)
    job = troll(client, style="drill", intensity="nuclear", vocal_style="aggressive")
    made = outputs(client, job)
    assert set(made) == {"lyrics", "song", "artwork"}  # no spoken vocals, no separate beat, no mix
    assert voice.spoken == [] and singer.beats == 0
    request = singer.songs[0]
    assert [p.label for p in request.sections][:2] == ["Intro", "Verse 1"]
    assert "UK drill" in request.style_prompt and "aggressive, shouted rap vocals" in request.style_prompt
    assert "spoken word" in request.negative_style
    song_asset = made["song"]
    assert song_asset["meta"]["delivery"] == "sung" and song_asset["meta"]["lyrics_adherence"] == "unverified"
    assert song_asset["provider"] == "fake_singer" and song_asset["is_ai"] is True and song_asset["mime_type"] == "audio/mpeg"
    assert 5 <= song_asset["duration_seconds"] <= 7
    assert song_asset["meta"]["troll"]["performance"] == "sung" and song_asset["meta"]["troll"]["singer_fallback"] is False
    caps = {c["kind"]: c for c in client.get("/api/system/capabilities").json()}
    assert caps["music"]["sings"] is True


def test_a_failing_singer_falls_back_to_spoken_vocals_and_says_so(studio):  # noqa: F811
    singer = FakeSinger(fail=ProviderNotConfiguredError("ElevenLabs refused the request for this account: the Music API needs a paid plan."))
    client = studio(music=singer)
    made = outputs(client, troll(client))
    assert {"vocals", "beat", "song"} <= set(made)
    song_asset = made["song"]
    assert song_asset["meta"]["delivery"] == "spoken" and song_asset["meta"]["troll"]["singer_fallback"] is True
    warning = song_asset["meta"]["troll"]["warnings"][0]
    assert "AI singer failed" in warning and "paid plan" in warning
    assert made["beat"]["provider"] == "procedural" and singer.beats == 0  # the fallback beat is the free built-in one


def test_spoken_pipeline_is_unchanged_without_a_singer(studio):  # noqa: F811
    client = studio()
    made = outputs(client, troll(client))
    assert made["song"]["meta"]["delivery"] == "spoken" and made["song"]["meta"]["troll"]["performance"] == "spoken"
    caps = {c["kind"]: c for c in client.get("/api/system/capabilities").json()}
    assert caps["music"]["sings"] is False


def test_vocal_styles_are_validated_and_steer_the_style_prompt():
    with pytest.raises(ValueError):
        TrollRequest(situation=DAVE, vocal_style="celebrity-clone")
    pop = TrollRequest(situation=DAVE, style="pop", subgenre="kpop")
    assert pop.song_style.startswith("K-pop style idol anthem") and "female pop vocals" in pop.song_style
    battle = TrollRequest(situation=DAVE, kind="rap_battle", style="trap", vocal_style="deep")
    assert "two rappers trading verses" in battle.song_style and "deep, low male rap vocals" in battle.song_style
