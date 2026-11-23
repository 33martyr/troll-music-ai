"""The one-button meme endpoint, plus the fun little helpers the home screen uses."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import ProvidersDep, QueueDep, SessionDep, load_asset, submit_job
from backend.api.studio import _require_ffmpeg
from backend.core.errors import ApiError
from backend.models.schemas import FactoryBody, JobOut, RemixBody, TrollBody
from backend.models.tables import Asset, Project
from backend.services import factory_jobs, troll_jobs
from backend.services.assets import sources_of
from troll_music_ai import troll
from troll_music_ai.templates import TEMPLATES

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


@router.get("/templates")
def templates():
    """Roast templates: friend archetypes with a scenario, settings and prompt guidance."""
    return [template.model_dump() for template in TEMPLATES]


@router.post("/remix", response_model=JobOut, status_code=202)
def remix(body: RemixBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    """Make a finished troll again with a different style, intensity, delivery,
    rapper or voice. The lyrics are reused unless ``instruction`` (or a new
    delivery) asks for a rewrite; the original files are never touched."""
    asset = load_asset(session, body.asset_id)
    troll_meta = _troll_meta(session, asset)
    if troll_meta is None or not troll_meta.get("request"):
        raise ApiError(422, "not_a_troll", "Only results made on the home page can be remixed. Use the Workshop pages for others.")
    # Keep the stage name the original got, even if it was picked at random.
    old = troll.TrollRequest.model_validate(troll_meta["request"] | {"rapper_name": troll_meta.get("artist") or troll_meta["request"].get("rapper_name")})
    changes = {k: v for k, v in body.model_dump(include={"style", "intensity", "delivery", "rapper_name", "voice"}).items() if v}
    try:
        request = troll.TrollRequest.model_validate(old.model_dump() | changes)
    except ValueError as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    instruction = (body.instruction or "").strip()
    if request.delivery != old.delivery:
        instruction = " ".join(
            part for part in (instruction, f"Rewrite the delivery as {troll.DELIVERIES[request.delivery][1]}.") if part
        )
    if request.intensity != old.intensity:
        instruction = " ".join(part for part in (instruction, f"Change the roast intensity to {request.intensity.value}.") if part)
    _require_ffmpeg()
    providers.require("music")
    lyrics_id = troll_meta.get("lyrics_asset_id")
    if body.regenerate_sections:
        if not lyrics_id:
            raise ApiError(422, "validation_error", "This troll has no lyrics to rewrite.")
        known = {s.get("id") for s in (session.get(Asset, lyrics_id).content or {}).get("sections", [])}
        missing = [sid for sid in body.regenerate_sections if sid not in known]
        if missing:
            raise ApiError(404, "not_found", f"Section(s) not in these lyrics: {', '.join(missing)}.")
    if lyrics_id:
        providers.require("voice")
        if instruction or body.regenerate_sections:
            providers.require("text")
    params = {
        "request": request.model_dump(mode="json"),
        "with_video": body.with_video or bool(troll_meta.get("video_asset_id")),
        "with_cover": body.with_cover,
        "lyrics_asset_id": lyrics_id,
        "rewrite_instruction": instruction or None,
        "regenerate_sections": body.regenerate_sections,
        "section_instruction": body.section_instruction,
        "remix_of": asset.id,
    }
    return submit_job(session, queue, kind=troll_jobs.JOB_TROLL, project_id=asset.project_id, params=params)


@router.post("/factory", response_model=JobOut, status_code=202)
def factory(body: FactoryBody, session: SessionDep, queue: QueueDep):
    """Meme Factory: vertical/square/wide videos, the cover, a concert poster, an
    award card, a 'now playing' card and a reaction meme, as one job."""
    asset = load_asset(session, body.asset_id)
    track = asset
    if (asset.meta or {}).get("troll") is None:
        track = next((s for _, s in sources_of(session, asset.id) if (s.meta or {}).get("troll")), None)
    if track is None or track.kind not in ("song", "beat"):
        raise ApiError(422, "not_a_troll", "The Meme Factory works on results made on the home page.")
    if any(item.endswith("_video") for item in body.items):
        _require_ffmpeg()
    params = body.model_dump(mode="json") | {"asset_id": track.id}
    return submit_job(session, queue, kind=factory_jobs.JOB_FACTORY, project_id=track.project_id, params=params)


def _troll_meta(session, asset: Asset) -> dict | None:
    """The troll record lives on the song (or beat); a video points back to it."""
    if (asset.meta or {}).get("troll"):
        return asset.meta["troll"]
    for _, source in sources_of(session, asset.id):
        if (source.meta or {}).get("troll"):
            return source.meta["troll"]
    return None


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
