"""REST API tests. Jobs run inline, so a job is finished when the POST returns."""

from __future__ import annotations

import io
import json
import time
import zipfile

from fastapi.testclient import TestClient

from backend.models.tables import Job, JobStatus
from backend.workers.runner import fail_interrupted_jobs, queued_job_ids
from tests.conftest import SONG, ScriptedProvider
from troll_music_ai import ProviderUnavailableError

LYRICS_REQUEST = {"prompt": "A fake millionaire", "genre": "drill", "verses": 2}


def make_project(client, name="Diss Tape"):
    response = client.post("/api/projects", json={"name": name, "description": "vol. 1"})
    assert response.status_code == 201
    return response.json()


def generate(client, project_id=None, request=LYRICS_REQUEST):
    response = client.post("/api/lyrics/generate", json={"project_id": project_id, "request": request})
    assert response.status_code == 202, response.text
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "completed", job
    return client.get(f"/api/assets/{job['result_asset_id']}").json()


# ------------------------------ projects ---------------------------------- #


def test_project_crud(client):
    project = make_project(client)
    assert project["asset_counts"] == {}

    renamed = client.patch(f"/api/projects/{project['id']}", json={"name": "Diss Tape 2"}).json()
    assert renamed["name"] == "Diss Tape 2" and renamed["description"] == "vol. 1"
    assert [p["name"] for p in client.get("/api/projects").json()] == ["Diss Tape 2"]

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
    assert client.get("/api/projects").json() == []


def test_project_validation_and_error_shape(client):
    response = client.post("/api/projects", json={"name": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    missing = client.get("/api/projects/nope")
    assert missing.json() == {"error": {"code": "not_found", "message": "Project not found."}}


def test_deleting_a_project_deletes_its_assets(client):
    project = make_project(client)
    asset = generate(client, project["id"])
    client.delete(f"/api/projects/{project['id']}")
    assert client.get(f"/api/assets/{asset['id']}").status_code == 404


def test_duplicate_project_copies_assets_and_their_version_history(client):
    project = make_project(client)
    asset = generate(client, project["id"])
    client.put(
        f"/api/lyrics/{asset['id']}",
        json={"title": "Edited", "sections": [{"type": "verse", "label": "Verse 1", "lines": ["x"]}]},
    )

    copy = client.post(f"/api/projects/{project['id']}/duplicate").json()
    assert copy["name"] == "Diss Tape (copy)" and copy["asset_counts"] == {"lyrics": 1}

    originals = client.get(f"/api/projects/{project['id']}/assets?all_versions=true").json()
    copies = client.get(f"/api/projects/{copy['id']}/assets?all_versions=true").json()
    assert len(copies) == len(originals) == 2
    assert {a["id"] for a in copies}.isdisjoint({a["id"] for a in originals})
    latest = next(a for a in copies if a["is_latest"])
    first = next(a for a in copies if not a["is_latest"])
    assert latest["parent_id"] == first["id"] and latest["root_id"] == first["id"]

    # The copy is independent of the original.
    client.delete(f"/api/projects/{project['id']}")
    assert client.get(f"/api/assets/{latest['id']}").status_code == 200


def test_project_bundle_export(client):
    project = make_project(client)
    generate(client, project["id"])
    response = client.get(f"/api/projects/{project['id']}/export")
    assert response.status_code == 200
    assert 'filename="diss-tape.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        names = bundle.namelist()
        manifest = json.loads(bundle.read("project.json"))
    assert manifest["project"]["name"] == "Diss Tape" and len(manifest["assets"]) == 1
    assert sum(n.endswith(".md") for n in names) == 1 and sum(n.endswith(".txt") for n in names) == 1


# ------------------------------- lyrics ----------------------------------- #


def test_generate_lyrics_into_a_project(client):
    project = make_project(client)
    asset = generate(client, project["id"])

    assert asset["kind"] == "lyrics" and asset["project_id"] == project["id"]
    assert asset["version"] == 1 and asset["is_latest"] and asset["origin"] == "generated"
    assert asset["params"]["genre"] == "drill"
    assert asset["is_mock"] is True and asset["provider"] == "mock"  # the mock is labelled
    labels = [s["label"] for s in asset["content"]["sections"]]
    assert labels == ["Intro", "Verse 1", "Chorus", "Verse 2", "Chorus", "Outro"]
    assert client.get(f"/api/projects/{project['id']}").json()["asset_counts"] == {"lyrics": 1}


def test_lyrics_do_not_need_a_project(client):
    asset = generate(client)
    assert asset["project_id"] is None
    assert [a["id"] for a in client.get("/api/assets?kind=lyrics&unsorted=true").json()] == [asset["id"]]

    project = make_project(client)
    moved = client.patch(f"/api/assets/{asset['id']}", json={"project_id": project["id"]}).json()
    assert moved["project_id"] == project["id"]
    assert client.get("/api/assets?unsorted=true").json() == []


def test_generating_without_a_provider_is_a_clear_503_and_creates_nothing(make_client):
    client = make_client(None)
    response = client.post("/api/lyrics/generate", json={"request": LYRICS_REQUEST})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_not_configured"
    assert client.get("/api/assets").json() == []


def test_generate_rejects_invalid_input_and_unknown_projects(client):
    bad = client.post("/api/lyrics/generate", json={"request": {"prompt": "x", "troll_intensity": 9}})
    assert bad.status_code == 422
    missing = client.post("/api/lyrics/generate", json={"project_id": "nope", "request": LYRICS_REQUEST})
    assert missing.status_code == 404


def test_regenerate_section_adds_a_version_and_leaves_the_rest_alone(client):
    asset = generate(client)
    verse = asset["content"]["sections"][1]

    response = client.post(
        f"/api/lyrics/{asset['id']}/regenerate-section", json={"section_id": verse["id"]}
    )
    assert response.status_code == 202
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    updated = client.get(f"/api/assets/{job['result_asset_id']}").json()

    assert updated["version"] == 2 and updated["parent_id"] == asset["id"]
    assert updated["origin"] == "section_regenerated" and updated["params"] == asset["params"]
    for before, after in zip(asset["content"]["sections"], updated["content"]["sections"]):
        assert (before == after) == (before["id"] != verse["id"])

    history = client.get(f"/api/assets/{asset['id']}/history").json()
    assert [(a["version"], a["is_latest"]) for a in history] == [(2, True), (1, False)]
    # The original version is preserved exactly.
    assert client.get(f"/api/assets/{asset['id']}").json()["content"] == asset["content"]
    # Listings show one entry per lyric, not one per version.
    assert len(client.get("/api/assets?kind=lyrics").json()) == 1


def test_regenerate_unknown_section_is_404(client):
    asset = generate(client)
    response = client.post(f"/api/lyrics/{asset['id']}/regenerate-section", json={"section_id": "zz"})
    assert response.status_code == 404


def test_rewrite_creates_a_new_version(client):
    asset = generate(client)
    response = client.post(f"/api/lyrics/{asset['id']}/rewrite", json={"mode": "funnier"})
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    rewritten = client.get(f"/api/assets/{job['result_asset_id']}").json()
    assert rewritten["version"] == 2 and rewritten["origin"] == "rewritten"
    assert rewritten["title"] == asset["title"]
    assert "funnier rewrite" in rewritten["content"]["sections"][0]["lines"][0]


def test_manual_edit_is_saved_as_a_version_without_calling_the_model(make_client):
    provider = ScriptedProvider(SONG)
    client = make_client(provider)
    asset = generate(client)
    sections = asset["content"]["sections"]
    sections[1]["lines"] = ["My own bar", "   ", "Another one"]

    edited = client.put(
        f"/api/lyrics/{asset['id']}", json={"title": "My Title", "sections": sections}
    ).json()

    assert len(provider.requests) == 1  # only the original generation
    assert edited["version"] == 2 and edited["origin"] == "edited" and edited["title"] == "My Title"
    assert edited["content"]["sections"][1]["lines"] == ["My own bar", "Another one"]
    assert edited["content"]["sections"][1]["id"] == sections[1]["id"]
    assert edited["content"]["suggested_bpm"] == 142


def test_manual_edit_with_no_lines_is_rejected(client):
    asset = generate(client)
    response = client.put(
        f"/api/lyrics/{asset['id']}",
        json={"title": "T", "sections": [{"type": "verse", "label": "V", "lines": [" "]}]},
    )
    assert response.status_code == 422


def test_approve_and_export(client):
    asset = generate(client)
    approved = client.patch(f"/api/assets/{asset['id']}", json={"approved": True}).json()
    assert approved["approved"] is True

    text = client.get(f"/api/assets/{asset['id']}/export?format=txt")
    assert text.headers["content-type"].startswith("text/plain")
    assert text.text.startswith(asset["title"]) and "[Verse 1]" in text.text
    markdown = client.get(f"/api/assets/{asset['id']}/export?format=md")
    assert markdown.text.startswith(f"# {asset['title']}")
    assert ".md" in markdown.headers["content-disposition"]
    assert "mock provider" in markdown.text


def test_delete_lyrics_removes_every_version(client):
    asset = generate(client)
    response = client.post(f"/api/lyrics/{asset['id']}/rewrite", json={"mode": "more_savage"})
    second = client.get(f"/api/jobs/{response.json()['id']}").json()["result_asset_id"]
    assert client.delete(f"/api/assets/{second}").status_code == 204
    assert client.get(f"/api/assets/{asset['id']}").status_code == 404
    assert client.get("/api/assets").json() == []


# --------------------------- jobs and providers --------------------------- #


def test_provider_failure_becomes_a_failed_job_with_a_readable_error(make_client):
    client = make_client(ScriptedProvider(ProviderUnavailableError("Could not reach ollama.")))
    response = client.post("/api/lyrics/generate", json={"request": LYRICS_REQUEST})
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "failed" and job["result_asset_id"] is None
    assert job["error_code"] == "provider_unavailable" and job["error"] == "Could not reach ollama."
    assert client.get("/api/assets").json() == []


def test_unparseable_model_output_fails_the_job_and_saves_nothing(make_client):
    client = make_client(ScriptedProvider("lol no", "still no"))
    response = client.post("/api/lyrics/generate", json={"request": LYRICS_REQUEST})
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "failed" and job["error_code"] == "lyrics_parse_error"
    assert client.get("/api/assets").json() == []


def test_unexpected_errors_do_not_leak_internals(make_client):
    client = make_client(ScriptedProvider(RuntimeError("secret stack detail")))
    response = client.post("/api/lyrics/generate", json={"request": LYRICS_REQUEST})
    job = client.get(f"/api/jobs/{response.json()['id']}").json()
    assert job["status"] == "failed" and job["error_code"] == "internal_error"
    assert "secret" not in job["error"]


def test_a_restart_resumes_queued_jobs_and_fails_half_finished_ones(client):
    factory = client.app.state.session_factory
    with factory() as session:
        waiting, running = Job(kind="lyrics.generate"), Job(kind="lyrics.generate", status=JobStatus.PROCESSING)
        session.add_all([waiting, running])
        session.commit()
        waiting_id, running_id = waiting.id, running.id
    assert fail_interrupted_jobs(factory) == 1
    assert queued_job_ids(factory) == [waiting_id]  # never started: safe to run again
    with factory() as session:
        assert session.get(Job, running_id).error_code == "interrupted"  # may have called a paid provider
        assert session.get(Job, waiting_id).status == JobStatus.QUEUED


def test_queued_jobs_really_run_after_a_restart(settings):
    from backend.main import create_app
    from troll_music_ai.providers import MockTextProvider

    first = create_app(settings, text_provider=MockTextProvider(), inline_jobs=True)
    with TestClient(first) as client:
        factory = client.app.state.session_factory
        with factory() as session:
            job = Job(kind="lyrics.generate", params={"request": {"prompt": "a friend who never replies", "genre": "trap"}})
            session.add(job)
            session.commit()
            job_id = job.id
    # A second process with a real worker pool picks it up on startup.
    second = create_app(settings, text_provider=MockTextProvider(), inline_jobs=False)
    with TestClient(second) as client:
        for _ in range(100):
            status = client.get(f"/api/jobs/{job_id}").json()["status"]
            if status in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert status == "completed", client.get(f"/api/jobs/{job_id}").json()


def test_capabilities_distinguish_implemented_configured_and_mock(make_client):
    mock_caps = {c["kind"]: c for c in make_client(ScriptedProvider()).get("/api/system/capabilities").json()}
    assert mock_caps["text"]["configured"] and mock_caps["text"]["provider"] == "scripted"
    # Built-in engines serve music, voice and images out of the box, labelled as not AI.
    assert mock_caps["music"]["provider"] == "procedural" and mock_caps["music"]["is_ai"] is False
    assert mock_caps["voice"]["configured"] and mock_caps["image"]["provider"] == "typographic"
    # No AI video model is integrated, and the API says so.
    assert mock_caps["video"]["implemented"] is False and mock_caps["video"]["configured"] is False


def test_capabilities_flag_the_mock_and_the_unconfigured_state(client, make_client):
    text = client.get("/api/system/capabilities").json()[0]
    assert text["is_mock"] is True and "placeholder" in text["note"]
    assert client.post("/api/system/capabilities/text/check").json()["ok"] is True

    bare = make_client(None)
    assert bare.get("/api/system/capabilities").json()[0]["configured"] is False
    assert bare.post("/api/system/capabilities/text/check").json()["ok"] is False


def test_bad_provider_settings_do_not_stop_the_app_from_starting(settings):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    broken = settings.model_copy(update={"llm_provider": "openai"})  # no key, no model
    with TestClient(create_app(broken, inline_jobs=True)) as client:
        text = client.get("/api/system/capabilities").json()[0]
        assert text["configured"] is False and "TROLL_LLM_MODEL" in text["note"]
        assert client.get("/api/projects").status_code == 200


def test_api_key_is_never_returned(settings):
    from fastapi.testclient import TestClient

    from backend.main import create_app

    from backend.core.config import Settings

    configured = Settings(
        _env_file=None,
        database_url=settings.database_url,
        storage_dir=settings.storage_dir,
        llm_provider="openai_compatible",
        llm_base_url="http://llm.test/v1",
        llm_model="tiny",
        llm_api_key="sk-super-secret",
    )
    assert "sk-super-secret" not in repr(configured)
    with TestClient(create_app(configured, inline_jobs=True)) as client:
        body = client.get("/api/system/capabilities").text + client.get("/api/system/providers").text
        assert "tiny" in body and "sk-super-secret" not in body
        text = client.get("/api/system/providers").json()[0]
        assert text["has_api_key"] is True and "api_key" not in text


def test_the_queue_refuses_new_jobs_when_too_many_are_waiting(client, monkeypatch):
    from backend.api import deps

    monkeypatch.setattr(deps, "MAX_WAITING_JOBS", 2)
    factory = client.app.state.session_factory
    with factory() as session:
        session.add_all([Job(kind="lyrics.generate"), Job(kind="lyrics.generate", status=JobStatus.PROCESSING)])
        session.commit()
    response = client.post("/api/lyrics/generate", json={"request": {"prompt": "a friend who never replies"}})
    assert response.status_code == 429 and response.json()["error"]["code"] == "too_many_jobs"
