"""The one-button meme endpoint, plus the fun little helpers the home screen uses."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import ProvidersDep, QueueDep, SessionDep, submit_job
from backend.api.studio import _require_ffmpeg
from backend.models.schemas import JobOut, TrollBody
from backend.models.tables import Project
from backend.services import troll_jobs
from troll_music_ai import troll

router = APIRouter(prefix="/api/troll", tags=["troll"])


@router.get("/options")
def options():
    """Kinds, styles, intensities and delivery styles for the troll form."""
    return troll.options()


@router.get("/random")
def random_troll():
    """A random situation, kind, style and rapper name for the Random Troll button. No model involved."""
    return troll.random_troll()


@router.get("/rapper-name")
def rapper_name(target: str | None = None):
    """A ridiculous stage name, from a built-in word list (no model)."""
    return {"name": troll.rapper_name(target)}


@router.post("", response_model=JobOut, status_code=202)
def generate(body: TrollBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    """Make the whole thing: words, vocals, beat, mix, cover and (for meme videos) an MP4.

    Saves into ``project_id``, or into a new project named after the target.
    """
    request = body.request
    _require_ffmpeg()
    providers.require("music")
    if request.kind is not troll.TrollKind.FUNNY_BEAT:
        providers.require("text")
        providers.require("voice")
    project_id = body.project_id
    if not project_id:
        project = Project(
            name=f"{troll.KIND_LABELS[request.kind]}: {request.who}"[:120],
            description=request.situation,
        )
        session.add(project)
        session.commit()
        project_id = project.id
    return submit_job(
        session, queue, kind=troll_jobs.JOB_TROLL, project_id=project_id,
        params=body.model_dump(mode="json", exclude={"project_id"}),
    )
