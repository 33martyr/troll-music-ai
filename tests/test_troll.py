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


# ------------------------------- phase 1 ----------------------------------- #


def test_templates_fill_the_form_and_steer_the_prompt(studio):  # noqa: F811
    from troll_music_ai.templates import TEMPLATES, filled

    assert len(TEMPLATES) == 14 and len({t.id for t in TEMPLATES}) == 14
    for template in TEMPLATES:  # every template is a valid request once filled in
        TrollRequest.model_validate(filled(template, "Dave"))
    late = filled(next(t for t in TEMPLATES if t.id == "late"), "Dave")
    prompt = troll_messages(TrollRequest.model_validate(late | {"inside_jokes": ["the kebab incident"]}))[-1].content
    assert "ARCHETYPE: The Always Late Friend" in prompt and "the kebab incident" in prompt
    client = studio()
    listed = client.get("/api/troll/templates").json()
    assert [t["id"] for t in listed] == [t.id for t in TEMPLATES]
    assert client.post("/api/troll", json={"request": {"situation": DAVE, "template": "nope"}}).status_code == 422


def test_punchline_mode_offers_alternatives_and_saving_one_is_a_new_version(studio):  # noqa: F811
    client = studio()
    made = outputs(client, troll(client))
    lyrics = made["lyrics"]
    section = lyrics["content"]["sections"][1]
    original_line = section["lines"][0]
    reply = client.post(f"/api/lyrics/{lyrics['id']}/punchlines", json={"section_id": section["id"], "line_index": 0}).json()
    assert len(reply["options"]) == 5 and reply["is_mock"] is True and reply["current"] == section["lines"][0]
    assert client.post(f"/api/lyrics/{lyrics['id']}/punchlines", json={"section_id": section["id"], "line_index": 99}).status_code == 404

    sections = lyrics["content"]["sections"]
    sections[1]["lines"][0] = reply["options"][2]
    saved = client.put(f"/api/lyrics/{lyrics['id']}", json={"title": lyrics["title"], "sections": sections}).json()
    assert saved["version"] == 2 and saved["content"]["sections"][1]["lines"][0] == reply["options"][2]
    restored = client.post(f"/api/lyrics/{lyrics['id']}/restore").json()
    assert restored["version"] == 3 and restored["origin"] == "restored"
    assert restored["content"]["sections"][1]["lines"][0] == original_line
    assert [v["version"] for v in client.get(f"/api/assets/{lyrics['id']}/history").json()] == [3, 2, 1]


def test_remix_reuses_the_lyrics_and_changes_only_what_was_asked(studio):  # noqa: F811
    client = studio()
    first = troll(client, style="trap", rapper_name="Lil Overdraft")
    song = client.get(f"/api/assets/{first['result_asset_id']}").json()
    lyrics_id = song["meta"]["troll"]["lyrics_asset_id"]

    remix = done(client, client.post("/api/troll/remix", json={"asset_id": song["id"], "style": "opera", "rapper_name": "Sir Buffering"}))
    made = outputs(client, remix)
    assert "lyrics" not in made  # no new words: the original lyrics were reused
    meta = made["song"]["meta"]["troll"]
    assert meta["lyrics_asset_id"] == lyrics_id and meta["lyrics_reused"] and meta["remix_of"] == song["id"]
    assert made["beat"]["meta"]["genre"] == "opera" and meta["artist"] == "Sir Buffering"
    assert remix["project_id"] == first["project_id"]

    rewritten = outputs(client, done(client, client.post("/api/troll/remix", json={"asset_id": song["id"], "delivery": "news"})))
    assert rewritten["lyrics"]["origin"] == "rewritten" and rewritten["lyrics"]["version"] == 2
    assert rewritten["song"]["meta"]["troll"]["artist"] == "Lil Overdraft"  # the stage name survives a remix

    beat = client.get(f"/api/assets/{troll(client, kind='funny_beat')['result_asset_id']}").json()
    random_name = beat["meta"]["troll"]["artist"]
    again = outputs(client, done(client, client.post("/api/troll/remix", json={"asset_id": beat["id"], "style": "8-bit"})))
    assert again["beat"]["meta"]["troll"]["artist"] == random_name and again["beat"]["meta"]["genre"] == "chiptune"

    imported = client.post("/api/lyrics/import", json={"title": "Mine", "text": "line one\nline two"}).json()
    refused = client.post("/api/troll/remix", json={"asset_id": imported["id"], "style": "pop"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "not_a_troll"


def test_group_chat_roast_gives_each_person_their_section_and_voice(studio):  # noqa: F811
    voice = FakeVoice()
    client = studio(voice=voice)
    job = troll(
        client, kind="group_roast", group_name="Lads Holiday", inside_jokes=["the kebab incident"],
        people=[{"name": "Dave", "nickname": "Big D", "voice": "Ada"}, {"name": "Sam", "voice": "Bob"}],
    )
    lyrics = outputs(client, job)["lyrics"]["content"]
    assert [s["label"] for s in lyrics["sections"]] == ["Intro", "Dave", "Sam", "Chorus", "Outro"]
    timings = outputs(client, job)["song"]["meta"]["line_timings"]
    by_label = {}
    for line, spoken in zip(timings, voice.spoken):
        by_label.setdefault(line["label"], set()).add(spoken.voice)
    assert by_label["Dave"] == {"Ada"} and by_label["Sam"] == {"Bob"} and by_label["Intro"] == {None}


def test_nuclear_length_subgenre_and_instructions_reach_the_prompt():
    request = TrollRequest(situation=DAVE, intensity="nuclear", style="trap", subgenre="rage", length="long", instructions="  mention   the scooter ")
    prompt = troll_messages(request)[-1].content
    assert "NUCLEAR" in prompt and "never crossing" in prompt and "never who they ARE" in prompt
    assert "rage trap" in prompt and "mention the scooter" in prompt and "10 lines" in prompt
    assert troll_structure(request).count("Chorus") == 3
    assert troll_structure(request.model_copy(update={"length": "short"})) == ["Intro", "Verse 1", "Chorus", "Outro"]
    assert TrollRequest(situation=DAVE, style="pop", subgenre="rage").subgenre is None  # wrong style: dropped
    with pytest.raises(ValueError):
        TrollRequest(situation=DAVE, length="epic")


def test_skipped_choruses_are_restored_in_the_requested_order():
    from troll_music_ai.lyrics.service import conform_to_structure
    from troll_music_ai.lyrics import parse_lyrics

    raw = parse_lyrics('{"title": "T", "sections": [{"type": "verse", "label": "Verse 1", "lines": ["v"]}, '
                       '{"type": "chorus", "label": "Chorus", "lines": ["c1", "c2"]}]}')
    fixed = conform_to_structure(raw, ["Chorus", "Verse 1", "Chorus", "Chorus"])
    assert [s.label for s in fixed.sections] == ["Chorus", "Verse 1", "Chorus", "Chorus"]
    assert len({s.id for s in fixed.sections}) == 4 and fixed.sections[0].lines == ["c1", "c2"]
    odd = parse_lyrics('{"title": "T", "sections": [{"type": "verse", "label": "Bars", "lines": ["x"]}]}')
    assert conform_to_structure(odd, ["Intro", "Verse 1", "Chorus", "Outro"]) == odd  # too different: untouched
