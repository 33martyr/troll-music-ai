"""Phase 2: group chat roast verse redo, Roast Battle 2.0 (knockout, scorecard,
votes) and the Meme Factory. Real files, mock words: see test_troll.py."""

from __future__ import annotations

import io
import zipfile

from tests.test_studio import FakeVoice, done, studio  # noqa: F401  (fixture)
from tests.test_troll import DAVE, outputs, troll


def test_redo_one_persons_verse_keeps_everyone_elses(studio):  # noqa: F811
    client = studio()
    first = troll(client, kind="group_roast", people=[{"name": "Dave"}, {"name": "Sam"}], group_name="Lads")
    song = client.get(f"/api/assets/{first['result_asset_id']}").json()
    before = client.get(f"/api/assets/{song['meta']['troll']['lyrics_asset_id']}").json()
    sam = next(s for s in before["content"]["sections"] if s["label"] == "Sam")

    redo = done(client, client.post("/api/troll/remix", json={"asset_id": song["id"], "regenerate_sections": [sam["id"]]}))
    made = outputs(client, redo)
    after = made["lyrics"]
    assert after["origin"] == "section_regenerated" and after["root_id"] == before["root_id"]
    for old, new in zip(before["content"]["sections"], after["content"]["sections"]):
        assert (new["lines"] != old["lines"]) == (old["id"] == sam["id"])
    assert made["song"]["meta"]["troll"]["lyrics_asset_id"] == after["id"]

    missing = client.post("/api/troll/remix", json={"asset_id": song["id"], "regenerate_sections": ["nope"]})
    assert missing.status_code == 404


def test_battle_has_a_knockout_round_scorecard_and_votes(studio):  # noqa: F811
    client = studio()
    job = troll(client, kind="rap_battle", rapper_name="MC Receipt", target="Dave")
    song_id = job["result_asset_id"]
    labels = [s["label"] for s in outputs(client, job)["lyrics"]["content"]["sections"]]
    assert "MC Receipt: Knockout" in labels and "Dave: Knockout" in labels
    assert outputs(client, job)["artwork"]["title"]  # cover billed as a match-up

    battle = client.get(f"/api/battles/{song_id}").json()
    assert battle["rappers"] == ["MC Receipt", "Dave"] and battle["scorecard"] is None
    assert battle["votes"] == {"counts": {}, "total": 0, "your_vote": None}

    card = client.post(f"/api/battles/{song_id}/score")
    assert card.status_code == 201
    card = card.json()
    assert card["kind"] == "scorecard" and card["is_mock"] is True and card["meta"]["opinion"] is True
    content = card["content"]
    assert set(content["scores"]) == {"MC Receipt", "Dave"} and content["winner"] == "MC Receipt"
    assert content["overall"]["MC Receipt"] == 5.2 and content["announcement"]
    assert client.get(f"/api/battles/{song_id}").json()["scorecard"]["id"] == card["id"]

    voter = "voter-1234-abcd"
    assert client.post(f"/api/battles/{song_id}/votes", json={"choice": "Dave", "voter_id": voter}).json()["counts"] == {"Dave": 1}
    tally = client.post(f"/api/battles/{song_id}/votes", json={"choice": "MC Receipt", "voter_id": voter}).json()
    assert tally == {"counts": {"MC Receipt": 1}, "total": 1, "your_vote": "MC Receipt"}  # changed, not added
    client.post(f"/api/battles/{song_id}/votes", json={"choice": "draw", "voter_id": "someone-else-99"})
    assert client.get(f"/api/battles/{song_id}/votes").json()["total"] == 2
    bad = client.post(f"/api/battles/{song_id}/votes", json={"choice": "Elvis", "voter_id": voter})
    assert bad.status_code == 422

    diss = troll(client)
    assert client.get(f"/api/battles/{diss['result_asset_id']}").status_code == 404


def test_meme_factory_makes_every_format_and_zips_them(studio):  # noqa: F811
    client = studio()
    job = troll(client, rapper_name="Lil Overdraft")
    song = client.get(f"/api/assets/{job['result_asset_id']}").json()
    cover_id = song["meta"]["troll"]["cover_asset_id"]
    items = ["vertical_video", "square_video", "wide_video", "square_cover", "concert_poster", "award_card", "streaming_card", "reaction_meme"]
    run = done(client, client.post("/api/troll/factory", json={"asset_id": song["id"], "items": items, "theme": "gold", "award": "Legendary Roast"}))
    made = [client.get(f"/api/assets/{i}").json() for i in run["result_asset_ids"]]

    videos = {a["meta"]["format"]: a for a in made if a["kind"] == "video"}
    assert {(v["meta"]["width"], v["meta"]["height"]) for v in videos.values()} == {(720, 1280), (1024, 1024), (1280, 720)}
    assert cover_id in run["result_asset_ids"]  # reused, not remade
    designs = {a["meta"]["format"]: a for a in made if a["kind"] == "artwork" and a["id"] != cover_id}
    assert set(designs) == {"concert_poster", "award_card", "streaming_card", "reaction_meme"}
    for design in designs.values():
        assert design["meta"]["parody"] is True and design["is_ai"] is False and design["mime_type"] == "image/png"
    assert designs["award_card"]["meta"]["award"] == "Legendary Roast"

    archive = client.post("/api/assets/zip", json={"asset_ids": run["result_asset_ids"], "name": "Dave pack"})
    assert archive.status_code == 200 and archive.headers["content-disposition"].endswith('"dave-pack.zip"')
    names = zipfile.ZipFile(io.BytesIO(archive.content)).namelist()
    assert len(names) == 8 and sum(n.endswith(".mp4") for n in names) == 3

    imported = client.post("/api/lyrics/import", json={"title": "Mine", "text": "a line\nanother"}).json()
    refused = client.post("/api/troll/factory", json={"asset_id": imported["id"], "items": ["award_card"]})
    assert refused.status_code == 422
    assert client.post("/api/troll/factory", json={"asset_id": song["id"], "items": []}).status_code == 422


def test_factory_works_for_a_funny_beat_without_lyrics(studio):  # noqa: F811
    client = studio(text=None)
    job = troll(client, kind="funny_beat", style="circus", situation=DAVE)
    run = done(client, client.post("/api/troll/factory", json={"asset_id": job["result_asset_id"], "items": ["reaction_meme", "concert_poster"]}))
    assert len(run["result_asset_ids"]) == 2
