"""The one-button meme flow: toolkit vocabulary, prompts and the full troll job.

The job tests run the real pipeline (procedural beats, FFmpeg, Pillow) with the
mock text provider and a fake voice, so the files are real but the words are
placeholders. Nothing here proves an AI model writes good roasts.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.conftest import SONG, ScriptedProvider
from tests.test_studio import FakeVoice, done, studio  # noqa: F401  (fixture)
from troll_music_ai import TrollKind, TrollRequest, random_troll, rapper_name
from troll_music_ai.errors import ProviderUnavailableError
from troll_music_ai.lyrics import LyricsService, battle_request_for, lyrics_request_for, troll_structure
from troll_music_ai.lyrics.prompts import troll_messages
from troll_music_ai.providers import ImageGenerationProvider, ProviderInfo, ProviderKind, ProviderStatus
from troll_music_ai.troll import STYLES, guess_name

DAVE = "My friend Dave thinks he's rich but borrows money every Friday"


# ------------------------------- toolkit ---------------------------------- #


def test_names_are_found_in_the_situation():
    assert guess_name(DAVE) == "Dave"
    assert guess_name("When my flatmate forgets the bins on Monday") is None
    assert TrollRequest(situation=DAVE).who == "Dave"
    assert TrollRequest(situation="someone ate my lunch").who == "Your Friend"
    assert TrollRequest(situation=DAVE, target="  Big   D ").who == "Big D"


@pytest.mark.parametrize("field,value", [("style", "dubstep-polka"), ("delivery", "mime"), ("situation", "  ")])
def test_bad_choices_are_rejected(field, value):
    with pytest.raises(ValueError):
        TrollRequest(**{"situation": DAVE, field: value})


def test_each_kind_has_its_own_shape():
    shape = lambda kind, **extra: troll_structure(TrollRequest(situation=DAVE, kind=kind, **extra))  # noqa: E731
    assert shape("roast") == ["Intro", "Roast", "Outro"]
    assert shape("meme_song").count("Chorus") == 3
    assert shape("group_roast", names=["Dave", "Sam", "Dave"]) == ["Intro", "Dave", "Sam", "Chorus", "Outro"]
    assert shape("diss_track") == ["Intro", "Verse 1", "Chorus", "Verse 2", "Chorus", "Outro"]


def test_prompt_carries_the_choices_and_the_friendship_rules():
    request = TrollRequest(situation=DAVE, kind="roast", style="opera", intensity="brutal", delivery="narrator", rapper_name="Lil Overdraft")
    prompt = troll_messages(request)[-1].content
    assert "TASK: generate_troll" in prompt and "TARGET: Dave" in prompt
    assert "opera" in prompt and "BRUTAL" in prompt and "Lil Overdraft" in prompt and "narrator" in prompt
    assert "never who they ARE" in prompt and "clean, no profanity" in prompt


def test_random_trolls_and_rapper_names_are_valid():
    for seed in range(20):
        idea = random_troll(seed=seed)
        assert TrollRequest.model_validate(idea).situation
        assert rapper_name("Dave", seed=seed).strip()
    assert all(style in STYLES for style in ("drill", "trap", "hip-hop", "pop", "country", "opera", "techno"))


def test_generate_troll_and_the_derived_requests():
    provider = ScriptedProvider(SONG)
    request = TrollRequest(situation=DAVE, kind="diss_track", intensity="friendly")
    lyrics = asyncio.run(LyricsService(provider).generate_troll(request))
    assert lyrics.title == "Lambo On Layaway" and "generate_troll" in provider.requests[0].messages[-1].content
    assert lyrics_request_for(request).troll_intensity == 2
    battle = battle_request_for(request.model_copy(update={"rapper_name": "MC Receipt"}))
    assert (battle.character_a.name, battle.character_b.name) == ("MC Receipt", "Dave")
    with pytest.raises(ValueError):
        asyncio.run(LyricsService(provider).generate_troll(request.model_copy(update={"kind": TrollKind.FUNNY_BEAT})))


# ---------------------------------- API ----------------------------------- #


def troll(client, **request):
    body = {"request": {"situation": DAVE, "kind": "diss_track", "style": "trap", **request.pop("request", {}), **request}}
    return done(client, client.post("/api/troll", json=body))


def outputs(client, job) -> dict[str, dict]:
    return {a["kind"]: a for a in (client.get(f"/api/assets/{i}").json() for i in job["result_asset_ids"])}


def test_one_button_diss_track_makes_lyrics_vocals_beat_song_and_cover(studio):  # noqa: F811
    client = studio()
    job = troll(client, intensity="savage", rapper_name="Lil Overdraft")
    made = outputs(client, job)
    assert set(made) == {"lyrics", "vocals", "beat", "song", "artwork"}
    song = made["song"]
    assert job["result_asset_id"] == song["id"] and song["has_file"] and song["mime_type"] == "audio/mpeg"
    assert song["meta"]["delivery"] == "spoken"  # honest label survives the one-button flow
    assert made["lyrics"]["is_mock"] is True  # mock words are still labelled as mock
    assert made["beat"]["meta"]["bpm"] == 140 and made["beat"]["duration_seconds"] >= made["vocals"]["duration_seconds"]
    troll_meta = song["meta"]["troll"]
    assert troll_meta["artist"] == "Lil Overdraft" and troll_meta["target"] == "Dave"
    assert troll_meta["cover_asset_id"] == made["artwork"]["id"] and made["artwork"]["meta"]["meme_overlay"] is True
    project = client.get(f"/api/projects/{job['project_id']}").json()
    assert project["name"] == "Diss Track: Dave"
    # Regenerating into the same project keeps everything together.
    again = done(client, client.post("/api/troll", json={"project_id": job["project_id"], "request": {"situation": DAVE}}))
    assert again["project_id"] == job["project_id"] and len(client.get("/api/projects").json()) == 1


def test_meme_video_renders_a_vertical_mp4_with_a_dramatic_intro(studio):  # noqa: F811
    client = studio()
    job = troll(client, kind="meme_video", style="techno")
    video = client.get(f"/api/assets/{job['result_asset_id']}").json()
    assert video["kind"] == "video" and video["mime_type"] == "video/mp4"
    assert (video["meta"]["width"], video["meta"]["height"]) == (720, 1280)
    assert video["meta"]["intro_card"] is True and video["meta"]["renderer"] == "ffmpeg-stills"


def test_rap_battle_gives_the_friend_the_second_voice(studio):  # noqa: F811
    voice = FakeVoice()
    client = studio(voice=voice)
    job = troll(client, kind="rap_battle", rapper_name="MC Receipt", target="Dave")
    lyrics = outputs(client, job)["lyrics"]["content"]
    performers = {s["performer"] for s in lyrics["sections"]} - {None}
    assert performers == {"MC Receipt", "Dave"}
    assert {line.voice for line in voice.spoken} == {None, "Bob"}


def test_funny_beat_needs_no_text_model(studio):  # noqa: F811
    client = studio(text=None)
    job = troll(client, kind="funny_beat", style="circus", target="Dave")
    made = outputs(client, job)
    assert set(made) == {"beat", "artwork"}
    assert "Dave" in made["beat"]["title"] and made["beat"]["meta"]["genre"] == "circus"


def test_missing_text_model_is_refused_before_anything_is_created(studio):  # noqa: F811
    client = studio(text=None)
    response = client.post("/api/troll", json={"request": {"situation": DAVE}})
    assert response.status_code == 503 and response.json()["error"]["code"] == "provider_not_configured"
    assert client.get("/api/projects").json() == []


class BrokenImages(ImageGenerationProvider):
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="broken_images", kind=ProviderKind.IMAGE, model="x")

    async def check(self) -> ProviderStatus:
        return ProviderStatus(ok=False, detail="down")

    async def generate_image(self, request, out_path):
        raise ProviderUnavailableError("Image server is down.")


def test_a_failing_cover_does_not_lose_the_song(studio):  # noqa: F811
    client = studio(image=BrokenImages())
    job = troll(client, kind="meme_song")
    song = client.get(f"/api/assets/{job['result_asset_id']}").json()
    assert song["kind"] == "song" and song["meta"]["troll"]["cover_asset_id"] is None
    assert "Image server is down" in song["meta"]["troll"]["warnings"][0]


def test_form_helpers(studio):  # noqa: F811
    client = studio()
    options = client.get("/api/troll/options").json()
    assert {k["id"] for k in options["kinds"]} >= {"diss_track", "roast", "rap_battle", "meme_song", "funny_beat", "meme_video"}
    assert TrollRequest.model_validate(client.get("/api/troll/random").json())
    assert client.get("/api/troll/rapper-name?target=Dave").json()["name"]
    assert client.post("/api/troll", json={"request": {"situation": DAVE, "style": "polka"}}).status_code == 422
