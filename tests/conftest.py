from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.core.config import Settings
from backend.main import create_app
from troll_music_ai.providers import (
    MockTextProvider,
    ProviderInfo,
    ProviderKind,
    ProviderStatus,
    TextGenerationProvider,
    TextRequest,
    TextResult,
)

SONG = {
    "title": "Lambo On Layaway",
    "suggested_bpm": 142,
    "suggested_genre": "drill",
    "beat_notes": ["sliding 808s", "dark piano"],
    "sections": [
        {"type": "intro", "label": "Intro", "lines": ["Yeah", "Check the receipt"]},
        {"type": "verse", "label": "Verse 1", "lines": ["Rented the whip", "Returned it by six"]},
        {"type": "chorus", "label": "Chorus", "lines": ["Fake it", "Till the card declines"]},
        {"type": "verse", "label": "Verse 2", "lines": ["Crypto guru", "Lives with his mum"]},
        {"type": "chorus", "label": "Chorus", "lines": ["Fake it", "Till the card declines"]},
        {"type": "outro", "label": "Outro", "lines": ["Declined"]},
    ],
}


class ScriptedProvider(TextGenerationProvider):
    """Returns queued replies in order. An exception in the queue is raised."""

    def __init__(self, *replies: str | dict | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[TextRequest] = []

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(name="scripted", kind=ProviderKind.TEXT, model="scripted-1")

    async def check(self) -> ProviderStatus:
        return ProviderStatus(ok=True, detail="ok")

    async def generate_text(self, request: TextRequest) -> TextResult:
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return TextResult(text=text, model="scripted-1")


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        storage_dir=str(tmp_path / "storage"),
    )


@pytest.fixture
def make_client(settings):
    clients = []

    def _make(provider: TextGenerationProvider | None) -> TestClient:
        client = TestClient(create_app(settings, text_provider=provider, inline_jobs=True))
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client(MockTextProvider())
