"""Application factory.

Run locally with::

    uvicorn backend.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import assets, battle, jobs, lyrics, projects, studio, system, troll, universe, voices
from backend.audio import ffmpeg
from backend.core import security
from backend.core.config import Settings, get_settings
from backend.core.db import create_schema, make_engine, make_session_factory
from backend.core.errors import install_error_handlers
from backend.core.storage import LocalStorage
from backend.services import audio_jobs, factory_jobs, troll_jobs, universe_jobs, visual_jobs
from backend.services import lyrics as lyrics_jobs
from backend.services.providers import ProviderManager
from backend.workers.queue import InlineJobQueue, ThreadPoolJobQueue
from backend.workers.runner import JobRunner, fail_interrupted_jobs
from troll_music_ai.providers import Provider, TextGenerationProvider

log = logging.getLogger(__name__)
_FROM_SETTINGS: Any = object()


def create_app(
    settings: Settings | None = None,
    *,
    text_provider: TextGenerationProvider | None = _FROM_SETTINGS,
    providers: dict[str, Provider | None] | None = None,
    inline_jobs: bool = False,
) -> FastAPI:
    """Build the app.

    ``text_provider``, ``providers`` (overrides keyed by kind: text, music,
    voice, image) and ``inline_jobs`` exist for tests.
    """
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    create_schema(engine)
    session_factory = make_session_factory(engine)

    overrides = dict(providers or {})
    if text_provider is not _FROM_SETTINGS:
        overrides["text"] = text_provider
    manager = ProviderManager(settings, session_factory, overrides)
    storage = LocalStorage(settings.storage_dir)
    ffmpeg.configure(settings.ffmpeg_path)
    security.configure(settings.api_key.get_secret_value() if settings.api_key else None)

    handlers = {**lyrics_jobs.HANDLERS, **audio_jobs.HANDLERS, **visual_jobs.HANDLERS, **troll_jobs.HANDLERS, **factory_jobs.HANDLERS, **universe_jobs.HANDLERS}
    runner = JobRunner(session_factory, handlers, manager, storage)
    queue = (
        InlineJobQueue(runner.run)
        if inline_jobs
        else ThreadPoolJobQueue(runner.run, workers=settings.job_workers)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        interrupted = fail_interrupted_jobs(session_factory)
        if interrupted:
            log.warning("Marked %d interrupted job(s) as failed", interrupted)
        ok, detail = ffmpeg.available()
        if not ok:
            log.warning("FFmpeg not found: audio and video features are disabled. %s", detail)
        yield
        queue.shutdown()
        engine.dispose()

    app = FastAPI(
        title="TROLL-MUSIC-AI",
        version="0.3.0",
        description="Roast it. Rap it. Release it.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.job_queue = queue
    app.state.providers = manager
    app.state.storage = storage

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    install_error_handlers(app)

    @app.get("/api/health", tags=["system"])
    def health():
        """Open even when an API key is set, and says whether one is needed."""
        return {"status": "ok", "auth_required": bool(settings.api_key)}

    # Everything else sits behind the API key when TROLL_API_KEY is set.
    guard = [Depends(security.require_api_key)]
    for module in (system, projects, assets, lyrics, battle, studio, troll, universe, voices, jobs):
        app.include_router(module.router, dependencies=guard)
    return app


def __getattr__(name: str) -> FastAPI:
    # Lazy so importing this module in tests does not touch the real database.
    if name == "app":
        global app
        app = create_app()
        return app
    raise AttributeError(name)
