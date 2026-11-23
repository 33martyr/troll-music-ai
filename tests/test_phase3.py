"""Phase 3: Troll Universe (rappers, cards, rivalries, records) and Roast Awards."""

from __future__ import annotations

import asyncio

import pytest

from backend.models.tables import RivalryResult
from tests.conftest import ScriptedProvider
from tests.test_studio import FakeVoice, done, studio  # noqa: F401  (fixture)
from tests.test_troll import outputs, troll
from troll_music_ai import LyricsParseError
from troll_music_ai.lyrics import LyricsService
from troll_music_ai.universe import AWARDS, parse_awards, parse_profile, random_profile


def test_profile_and_awards_parsing():
    profile = parse_profile('{"name": " MC  Stub ", "style": "polka", "delivery": "mime", "stats": {"flow": 140, "comedy": "x"}}')
    assert profile.name == "MC Stub" and profile.style == "trap" and profile.delivery == "cocky"
    assert profile.stats.flow == 99 and profile.stats.comedy == 50
    with pytest.raises(LyricsParseError):
        parse_profile('{"name": ""}')
    awards = parse_awards('{"awards": [{"award": "best punchline", "reason": "r", "line": "l"}, {"award": "Grammy", "reason": "x"}, {"award": "Best Punchline", "reason": "dupe"}]}')
    assert [a.award for a in awards] == ["Best Punchline"] and awards[0].line == "l"
    assert random_profile(seed=1).name and len(AWARDS) == 8
    rapper = asyncio.run(LyricsService(ScriptedProvider({"name": "Lil Test", "stats": {}})).create_rapper("a sleepy DJ"))
    assert rapper.name == "Lil Test"


def make_rapper(client, **body) -> dict:
    response = client.post("/api/universe/rappers", json={"name": "Lil Overdraft", "personality": "borrows everything", **body})
    assert response.status_code == 201, response.text
    return response.json()


def test_rappers_are_created_edited_and_get_cards(studio):  # noqa: F811
    client = studio()
    ai = client.post("/api/universe/rappers/generate", json={"idea": "a gym bro who raps about protein"}).json()
    assert ai["origin"] == "ai" and ai["is_mock"] is True and ai["card"]["mime_type"] == "image/png"
    builtin = studio(text=None).post("/api/universe/rappers/generate", json={}).json()
    assert builtin["origin"] == "builtin" and builtin["is_mock"] is False and builtin["name"]

    mine = make_rapper(client, style="drill", stats={"punchline": 90, "flow": 70, "comedy": 80, "creativity": 60, "reputation": 10})
    assert mine["overall"] == 62 and mine["origin"] == "manual"
    edited = client.patch(f"/api/universe/rappers/{mine['id']}", json={"catchphrase": "Receipt printed.", "stats": {"reputation": 60}}).json()
    assert edited["catchphrase"] == "Receipt printed." and edited["card"]["id"] != mine["card"]["id"]
    assert client.patch(f"/api/universe/rappers/{mine['id']}", json={"style": "polka"}).status_code == 422
    assert {r["id"] for r in client.get("/api/universe/rappers").json()} >= {ai["id"], mine["id"]}

    job = done(client, client.post(f"/api/universe/rappers/{mine['id']}/portrait"))
    painted = client.get(f"/api/universe/rappers/{mine['id']}").json()
    assert painted["avatar"]["meta"]["format"] == "rapper_avatar" and painted["card"]["id"] == job["result_asset_id"]


def test_rivalry_battles_settle_into_records_and_titles(studio):  # noqa: F811
    voice = FakeVoice()
    client = studio(voice=voice)
    a = make_rapper(client, name="Lil Overdraft", voice="Ada")
    b = make_rapper(client, name="Sir Buffering", personality="always loading", voice="Bob")
    assert client.post("/api/universe/rivalries", json={"rapper_a_id": a["id"], "rapper_b_id": a["id"]}).status_code == 422
    rivalry = client.post("/api/universe/rivalries", json={"rapper_a_id": a["id"], "rapper_b_id": b["id"], "tagline": "Who owes who?"}).json()

    job = done(client, client.post(f"/api/universe/rivalries/{rivalry['id']}/tracks", json={"kind": "battle"}))
    made = outputs(client, job)
    performers = {s["performer"] for s in made["lyrics"]["content"]["sections"]} - {None}
    assert performers == {"Lil Overdraft", "Sir Buffering"} and {line.voice for line in voice.spoken} == {"Ada", "Bob"}
    song_id = made["song"]["id"]
    history = client.get(f"/api/universe/rivalries/{rivalry['id']}").json()["history"]
    assert [h["track"]["id"] for h in history] == [song_id] and history[0]["settled"] is False

    undecided = client.post(f"/api/universe/rivalries/{rivalry['id']}/settle", json={"song_asset_id": song_id})
    assert undecided.status_code == 422 and undecided.json()["error"]["code"] == "undecided"
    client.post(f"/api/battles/{song_id}/score")  # mock judges always pick rapper A
    settled = client.post(f"/api/universe/rivalries/{rivalry['id']}/settle", json={"song_asset_id": song_id}).json()
    assert settled["record"] == {"a": 1, "b": 0, "draws": 0} and settled["history"][0]["source"] == "judges"
    # Friends' votes beat the judges.
    client.post(f"/api/battles/{song_id}/votes", json={"choice": "Sir Buffering", "voter_id": "friend-0001"})
    settled = client.post(f"/api/universe/rivalries/{rivalry['id']}/settle", json={"song_asset_id": song_id}).json()
    assert settled["record"] == {"a": 0, "b": 1, "draws": 0} and settled["history"][0]["source"] == "votes"

    # Two more wins make a champion (results added directly to skip rendering two more battles).
    factory = client.app.state.session_factory
    with factory() as session:
        for index in range(2):
            session.add(RivalryResult(rivalry_id=rivalry["id"], song_asset_id=f"fake{index}", winner_id=b["id"], source="manual"))
        session.commit()
    final = client.post(f"/api/universe/rivalries/{rivalry['id']}/settle", json={"song_asset_id": song_id, "winner": b["id"]}).json()
    assert final["record"]["b"] == 3 and final["champion_id"] == b["id"]
    champ = client.get(f"/api/universe/rappers/{b['id']}").json()
    assert (champ["wins"], champ["losses"]) == (3, 0) and champ["titles"] == ["Champion over Lil Overdraft"]
    assert client.get(f"/api/universe/rappers/{a['id']}").json()["losses"] == 3

    diss = done(client, client.post(f"/api/universe/rivalries/{rivalry['id']}/tracks", json={"kind": "diss", "from_id": b["id"]}))
    assert outputs(client, diss)["song"]["meta"]["troll"]["artist"] == "Sir Buffering"
    assert client.post(f"/api/universe/rivalries/{rivalry['id']}/tracks", json={"kind": "diss"}).status_code == 422
    poster = client.post(f"/api/universe/rivalries/{rivalry['id']}/poster").json()
    assert poster["meta"]["format"] == "rivalry_poster" and poster["mime_type"] == "image/png"

    assert client.delete(f"/api/universe/rappers/{a['id']}").status_code == 204
    assert client.get("/api/universe/rivalries").json() == []
    assert client.get(f"/api/universe/rappers/{b['id']}").json()["wins"] == 0


def test_roast_awards_make_cards_from_the_fixed_list(studio):  # noqa: F811
    client = studio()
    job = troll(client)
    song_id = job["result_asset_id"]
    awards_job = done(client, client.post(f"/api/awards/{song_id}", json={"count": 3, "theme": "gold"}))
    cards = client.get(f"/api/awards/{song_id}").json()
    assert len(cards) == 3 == len(awards_job["result_asset_ids"])
    for card in cards:
        assert card["meta"]["award"] in AWARDS and card["meta"]["parody"] and card["meta"]["judged_mock"] is True
        assert card["is_mock"] is True and card["mime_type"] == "image/png"
    assert studio(text=None).post(f"/api/awards/{song_id}", json={}).status_code == 503
