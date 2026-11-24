"""Troll Universe (fictional rappers, rivalries, cards) and Roast Awards.

Everything here is private to this installation: there are no public rapper
profiles. Rappers are always fictional; the prompts say so.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.deps import ProvidersDep, QueueDep, SessionDep, StorageDep, load_asset, submit_job
from backend.api.studio import _require_ffmpeg
from backend.core.errors import ApiError, not_found
from backend.models.schemas import AssetOut, JobOut
from backend.models.tables import Asset, AssetKind, Project, Rapper, Rivalry, RivalryResult
from backend.services import troll_jobs, universe_jobs
from troll_music_ai.lyrics import LyricsService
from troll_music_ai.troll import DELIVERIES, STYLES, TrollRequest
from troll_music_ai.universe import RapperProfile, RapperStats, random_profile

router = APIRouter(prefix="/api", tags=["universe"])


# --------------------------------- schemas --------------------------------- #


class RapperOut(BaseModel):
    id: str
    name: str
    personality: str
    style: str
    delivery: str
    catchphrase: str
    bio: str
    stats: dict
    overall: int
    voice: str | None
    avatar: AssetOut | None
    card: AssetOut | None
    wins: int
    losses: int
    draws: int
    titles: list[str]
    origin: str
    provider: str | None
    model: str | None
    is_mock: bool


class RapperPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    personality: str | None = Field(default=None, max_length=300)
    style: str | None = None
    delivery: str | None = None
    catchphrase: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=800)
    stats: RapperStats | None = None
    voice: str | None = Field(default=None, max_length=120)


class GenerateRapperBody(BaseModel):
    idea: str | None = Field(default=None, max_length=300)


class RivalryBody(BaseModel):
    rapper_a_id: str
    rapper_b_id: str
    tagline: str = Field(default="", max_length=300)


class RivalryTrackBody(BaseModel):
    kind: Literal["battle", "diss"] = "battle"
    from_id: str | None = Field(default=None, description="Diss tracks: who disses whom (the other rapper is the target).")
    situation: str | None = Field(default=None, max_length=600)
    style: str | None = None
    intensity: Literal["friendly", "savage", "brutal", "nuclear"] = "savage"
    with_video: bool = False


class SettleBody(BaseModel):
    song_asset_id: str
    winner: str | None = Field(default=None, description="A rapper id, 'draw', or empty to use votes then the judges.")


class AwardsBody(BaseModel):
    count: int = Field(default=3, ge=1, le=4)
    theme: Literal["neon", "gold", "vaporwave", "grunge", "comic"] = "gold"


def _out(session, rapper: Rapper) -> RapperOut:
    stats = RapperStats(**(rapper.stats or {}))
    avatar = session.get(Asset, rapper.avatar_asset_id) if rapper.avatar_asset_id else None
    card = session.get(Asset, rapper.card_asset_id) if rapper.card_asset_id else None
    return RapperOut(
        id=rapper.id, name=rapper.name, personality=rapper.personality, style=rapper.style, delivery=rapper.delivery,
        catchphrase=rapper.catchphrase, bio=rapper.bio, stats=stats.model_dump(), overall=stats.overall, voice=rapper.voice,
        avatar=AssetOut.model_validate(avatar) if avatar else None, card=AssetOut.model_validate(card) if card else None,
        wins=rapper.wins, losses=rapper.losses, draws=rapper.draws, titles=list(rapper.titles or []), origin=rapper.origin,
        provider=rapper.provider, model=rapper.model, is_mock=rapper.is_mock,
    )


def _load_rapper(session, rapper_id: str) -> Rapper:
    rapper = session.get(Rapper, rapper_id)
    if rapper is None:
        raise not_found("Rapper")
    return rapper


def _load_rivalry(session, rivalry_id: str) -> Rivalry:
    rivalry = session.get(Rivalry, rivalry_id)
    if rivalry is None:
        raise not_found("Rivalry")
    return rivalry


def _redraw_card(session, storage, rapper: Rapper) -> None:
    workdir = Path(tempfile.mkdtemp(prefix="troll-card-"))
    try:
        universe_jobs.render_rapper_card(session, storage, rapper, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _save(session, storage, profile: RapperProfile, *, origin: str, provider=None, model=None, is_mock=False) -> Rapper:
    rapper = Rapper(
        name=profile.name, personality=profile.personality, style=profile.style, delivery=profile.delivery,
        catchphrase=profile.catchphrase, bio=profile.bio, stats=profile.stats.model_dump(), voice=profile.voice,
        origin=origin, provider=provider, model=model, is_mock=is_mock,
    )
    session.add(rapper)
    session.flush()
    _redraw_card(session, storage, rapper)
    session.commit()
    return rapper


# --------------------------------- rappers --------------------------------- #


@router.get("/universe/rappers", response_model=list[RapperOut])
def list_rappers(session: SessionDep):
    return [_out(session, r) for r in session.scalars(select(Rapper).order_by(Rapper.created_at.desc()))]


@router.post("/universe/rappers", response_model=RapperOut, status_code=201)
def create_rapper(body: RapperProfile, session: SessionDep, storage: StorageDep):
    """A rapper you wrote yourself."""
    return _out(session, _save(session, storage, body, origin="manual"))


@router.post("/universe/rappers/generate", response_model=RapperOut, status_code=201)
def generate_rapper(body: GenerateRapperBody, session: SessionDep, storage: StorageDep, providers: ProvidersDep):
    """Invent a rapper from an idea with the text model. With no text model, a
    profile is built from word lists and marked ``origin: builtin`` (not AI)."""
    provider = providers.get("text")
    if provider is None:
        return _out(session, _save(session, storage, random_profile(body.idea), origin="builtin"))
    service = LyricsService(provider, json_mode=providers.json_mode())  # type: ignore[arg-type]
    profile = asyncio.run(service.create_rapper(body.idea))
    info = provider.info
    return _out(session, _save(session, storage, profile, origin="ai", provider=info.name, model=info.model, is_mock=info.is_mock))


@router.get("/universe/rappers/{rapper_id}", response_model=RapperOut)
def get_rapper(rapper_id: str, session: SessionDep):
    return _out(session, _load_rapper(session, rapper_id))


@router.patch("/universe/rappers/{rapper_id}", response_model=RapperOut)
def update_rapper(rapper_id: str, body: RapperPatch, session: SessionDep, storage: StorageDep):
    rapper = _load_rapper(session, rapper_id)
    changes = body.model_dump(exclude_unset=True)
    if "style" in changes and changes["style"] not in STYLES:
        raise ApiError(422, "validation_error", f"Unknown style. Choose one of: {', '.join(STYLES)}.")
    if "delivery" in changes and changes["delivery"] not in DELIVERIES:
        raise ApiError(422, "validation_error", f"Unknown delivery. Choose one of: {', '.join(DELIVERIES)}.")
    for key, value in changes.items():
        setattr(rapper, key, value)  # stats arrive as a validated dict
    if changes and rapper.origin != "manual":  # an empty patch only reprints the card
        rapper.origin = f"{rapper.origin}+edited" if not rapper.origin.endswith("+edited") else rapper.origin
    _redraw_card(session, storage, rapper)
    session.commit()
    return _out(session, rapper)


@router.delete("/universe/rappers/{rapper_id}", status_code=204)
def delete_rapper(rapper_id: str, session: SessionDep, storage: StorageDep):
    """Deletes the rapper and their rivalries. Tracks already made stay in My Trolls."""
    rapper = _load_rapper(session, rapper_id)
    rivalries = list(session.scalars(select(Rivalry).where((Rivalry.rapper_a_id == rapper.id) | (Rivalry.rapper_b_id == rapper.id))))
    others = set()
    for rivalry in rivalries:
        others.update({rivalry.rapper_a_id, rivalry.rapper_b_id} - {rapper.id})
        for result in session.scalars(select(RivalryResult).where(RivalryResult.rivalry_id == rivalry.id)):
            session.delete(result)
        session.delete(rivalry)
    session.delete(rapper)
    session.flush()
    for other_id in others:
        other = session.get(Rapper, other_id)
        if other:
            universe_jobs.recount(session, other)
            _redraw_card(session, storage, other)
    session.commit()
    return Response(status_code=204)


@router.post("/universe/rappers/{rapper_id}/portrait", response_model=JobOut, status_code=202)
def portrait(rapper_id: str, session: SessionDep, queue: QueueDep):
    """Paint a portrait with the image provider, then redraw the collectible card."""
    _load_rapper(session, rapper_id)
    return submit_job(session, queue, kind=universe_jobs.JOB_AVATAR, project_id=None, params={"rapper_id": rapper_id})


# -------------------------------- rivalries -------------------------------- #


def _rivalry_out(session, rivalry: Rivalry) -> dict:
    a, b = session.get(Rapper, rivalry.rapper_a_id), session.get(Rapper, rivalry.rapper_b_id)
    wins_a, wins_b, draws = universe_jobs.rivalry_record(session, rivalry)
    champion = universe_jobs.champion_of(session, rivalry)
    results = {r.song_asset_id: r for r in session.scalars(select(RivalryResult).where(RivalryResult.rivalry_id == rivalry.id))}
    tracks = [
        a_ for a_ in session.scalars(select(Asset).where(Asset.kind == AssetKind.SONG, Asset.project_id == rivalry.project_id).order_by(Asset.created_at.desc()))
        if ((a_.meta or {}).get("troll") or {}).get("rivalry_id") == rivalry.id
    ] if rivalry.project_id else []
    history = []
    for track in tracks:
        result = results.get(track.id)
        history.append({
            "track": AssetOut.model_validate(track),
            "kind": track.meta["troll"]["kind"],
            "settled": result is not None,
            "winner_id": result.winner_id if result else None,
            "source": result.source if result else None,
        })
    return {
        "id": rivalry.id,
        "tagline": rivalry.tagline,
        "project_id": rivalry.project_id,
        "rapper_a": _out(session, a).model_dump(mode="json"),
        "rapper_b": _out(session, b).model_dump(mode="json"),
        "record": {"a": wins_a, "b": wins_b, "draws": draws},
        "champion_id": champion.id if champion else None,
        "champion_wins_needed": universe_jobs.CHAMPION_WINS,
        "history": history,
    }


@router.get("/universe/rivalries")
def list_rivalries(session: SessionDep):
    return [_rivalry_out(session, r) for r in session.scalars(select(Rivalry).order_by(Rivalry.created_at.desc()))]


@router.post("/universe/rivalries", status_code=201)
def create_rivalry(body: RivalryBody, session: SessionDep):
    if body.rapper_a_id == body.rapper_b_id:
        raise ApiError(422, "validation_error", "A rapper can't feud with themself. (We checked.)")
    a, b = _load_rapper(session, body.rapper_a_id), _load_rapper(session, body.rapper_b_id)
    project = Project(name=f"Rivalry: {a.name} vs {b.name}"[:120], description=body.tagline)
    session.add(project)
    session.flush()
    rivalry = Rivalry(rapper_a_id=a.id, rapper_b_id=b.id, tagline=body.tagline.strip(), project_id=project.id)
    session.add(rivalry)
    session.commit()
    return _rivalry_out(session, rivalry)


@router.get("/universe/rivalries/{rivalry_id}")
def get_rivalry(rivalry_id: str, session: SessionDep):
    return _rivalry_out(session, _load_rivalry(session, rivalry_id))


@router.delete("/universe/rivalries/{rivalry_id}", status_code=204)
def delete_rivalry(rivalry_id: str, session: SessionDep, storage: StorageDep):
    rivalry = _load_rivalry(session, rivalry_id)
    ids = (rivalry.rapper_a_id, rivalry.rapper_b_id)
    for result in session.scalars(select(RivalryResult).where(RivalryResult.rivalry_id == rivalry.id)):
        session.delete(result)
    session.delete(rivalry)
    session.flush()
    for rapper_id in ids:
        rapper = session.get(Rapper, rapper_id)
        universe_jobs.recount(session, rapper)
        _redraw_card(session, storage, rapper)
    session.commit()
    return Response(status_code=204)


@router.post("/universe/rivalries/{rivalry_id}/tracks", response_model=JobOut, status_code=202)
def rivalry_track(rivalry_id: str, body: RivalryTrackBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    """A battle between the two rappers (two voices), or a diss track from one at the other."""
    rivalry = _load_rivalry(session, rivalry_id)
    a, b = session.get(Rapper, rivalry.rapper_a_id), session.get(Rapper, rivalry.rapper_b_id)
    _require_ffmpeg()
    for kind in ("text", "music", "voice"):
        providers.require(kind)
    character = lambda r: {"name": r.name, "personality": r.personality[:300], "style": DELIVERIES[r.delivery][0]}  # noqa: E731
    situation = body.situation or rivalry.tagline or f"{a.name} and {b.name} settle who is the better rapper"
    if body.kind == "battle":
        request = TrollRequest(
            situation=situation, kind="rap_battle", style=body.style or a.style, intensity=body.intensity,
            delivery=a.delivery, rapper_name=a.name, target=b.name, voice=a.voice, voice_b=b.voice,
            characters=[character(a), character(b)],
        )
    else:
        if body.from_id not in (a.id, b.id):
            raise ApiError(422, "validation_error", "Say who is dissing: from_id must be one of the two rappers.")
        me, them = (a, b) if body.from_id == a.id else (b, a)
        request = TrollRequest(
            situation=f"{situation}. {them.name}: {them.personality}"[:600], kind="diss_track", style=body.style or me.style,
            intensity=body.intensity, delivery=me.delivery, rapper_name=me.name, target=them.name, voice=me.voice,
        )
    params = {"request": request.model_dump(mode="json"), "with_video": body.with_video, "with_cover": True, "rivalry_id": rivalry.id}
    return submit_job(session, queue, kind=troll_jobs.JOB_TROLL, project_id=rivalry.project_id, params=params)


@router.post("/universe/rivalries/{rivalry_id}/settle")
def settle(rivalry_id: str, body: SettleBody, session: SessionDep, storage: StorageDep):
    """Record who won a battle: an explicit pick, else the friends' votes, else
    the AI judges' latest scorecard. Then update records and titles."""
    from backend.api.battle import _latest_scorecard, _lyrics_of, _tally

    rivalry = _load_rivalry(session, rivalry_id)
    song = load_asset(session, body.song_asset_id, AssetKind.SONG)
    if ((song.meta or {}).get("troll") or {}).get("rivalry_id") != rivalry.id or song.meta["troll"]["kind"] != "rap_battle":
        raise ApiError(422, "validation_error", "That battle is not part of this rivalry.")
    a, b = session.get(Rapper, rivalry.rapper_a_id), session.get(Rapper, rivalry.rapper_b_id)
    by_name = {a.name: a.id, b.name: b.id}
    if body.winner:
        if body.winner not in (a.id, b.id, "draw"):
            raise ApiError(422, "validation_error", "winner must be one of the two rapper ids or 'draw'.")
        winner, source = (None if body.winner == "draw" else body.winner), "manual"
    else:
        lyrics = _lyrics_of(session, song)
        votes = _tally(session, lyrics.root_id)["counts"]
        card = _latest_scorecard(session, lyrics)
        if votes:
            top = max(votes.values())
            leaders = [choice for choice, count in votes.items() if count == top]
            winner = by_name.get(leaders[0]) if len(leaders) == 1 and leaders[0] != "draw" else None
            source = "votes"
        elif card and card.content:
            winner, source = by_name.get(card.content.get("winner") or ""), "judges"
        else:
            raise ApiError(422, "undecided", "Nobody has voted and the judges haven't scored it. Vote or ask the judges first.")
    result = session.scalar(select(RivalryResult).where(RivalryResult.song_asset_id == song.id))
    if result:
        result.winner_id, result.source = winner, source
    else:
        session.add(RivalryResult(rivalry_id=rivalry.id, song_asset_id=song.id, winner_id=winner, source=source))
    session.flush()
    for rapper in (a, b):
        universe_jobs.recount(session, rapper)
        _redraw_card(session, storage, rapper)  # the card prints the record and titles
    session.commit()
    return _rivalry_out(session, rivalry)


@router.post("/universe/rivalries/{rivalry_id}/poster", response_model=AssetOut, status_code=201)
def poster(rivalry_id: str, session: SessionDep, storage: StorageDep):
    rivalry = _load_rivalry(session, rivalry_id)
    workdir = Path(tempfile.mkdtemp(prefix="troll-poster-"))
    try:
        asset = universe_jobs.render_rivalry_poster(session, storage, rivalry, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    session.commit()
    return asset


# --------------------------------- awards ---------------------------------- #


@router.post("/awards/{asset_id}", response_model=JobOut, status_code=202)
def make_awards(asset_id: str, body: AwardsBody, session: SessionDep, queue: QueueDep, providers: ProvidersDep):
    """Roast Awards: the text model picks awards for a track (an opinion) and each becomes an award card."""
    providers.require("text")
    track = load_asset(session, asset_id, (AssetKind.SONG, AssetKind.BEAT, AssetKind.VIDEO))
    params = {"asset_id": track.id, **body.model_dump()}
    return submit_job(session, queue, kind=universe_jobs.JOB_AWARDS, project_id=track.project_id, params=params)


@router.get("/awards/{asset_id}", response_model=list[AssetOut])
def list_awards(asset_id: str, session: SessionDep):
    track = load_asset(session, asset_id)
    cards = session.scalars(select(Asset).where(Asset.kind == AssetKind.ARTWORK, Asset.project_id == track.project_id).order_by(Asset.created_at.desc()))
    return [card for card in cards if (card.meta or {}).get("awards_for") == track.id]
