"""Roast Battle 2.0: the battle page's data, the AI judges' scorecard and votes.

A battle is identified by any of its assets (the song, the video or the battle
lyrics); everything resolves to the lyrics lineage, which keeps the rappers.
The scorecard is an AI model's opinion and is stored and labelled as one.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.api.deps import ProvidersDep, SessionDep, load_asset
from backend.core.errors import ApiError
from backend.models.schemas import AssetOut
from backend.models.tables import Asset, AssetKind, AssetLink, BattleVote
from backend.services.assets import create_asset, sources_of
from troll_music_ai import Lyrics
from troll_music_ai.lyrics import LyricsService

router = APIRouter(prefix="/api/battles", tags=["battles"])


class VoteBody(BaseModel):
    choice: str = Field(min_length=1, max_length=60, description="A rapper's name, or 'draw'.")
    voter_id: str = Field(min_length=8, max_length=64, description="A random id the voter keeps.")


def _lyrics_of(session, asset: Asset) -> Asset:
    """The newest battle lyrics behind any asset of the battle."""
    lyrics = asset if asset.kind == AssetKind.LYRICS else None
    if lyrics is None:
        troll_lyrics = ((asset.meta or {}).get("troll") or {}).get("lyrics_asset_id")
        lyrics = session.get(Asset, troll_lyrics) if troll_lyrics else None
    if lyrics is None:
        for relation, source in sources_of(session, asset.id):
            if relation == "lyrics":
                lyrics = source
            elif relation == "audio" and lyrics is None:
                lyrics = next((s for r, s in sources_of(session, source.id) if r == "lyrics"), None)
    if lyrics is None or "character_a" not in (lyrics.params or {}):
        raise ApiError(404, "not_a_battle", "That is not a rap battle.")
    latest = session.scalar(select(Asset).where(Asset.root_id == lyrics.root_id, Asset.is_latest.is_(True)))
    return latest or lyrics


def _rappers(lyrics: Asset) -> tuple[str, str]:
    params = lyrics.params or {}
    return params["character_a"]["name"], params["character_b"]["name"]


def _tally(session, battle_id: str, voter_id: str | None = None) -> dict:
    rows = session.execute(
        select(BattleVote.choice, func.count()).where(BattleVote.battle_id == battle_id).group_by(BattleVote.choice)
    ).all()
    mine = None
    if voter_id:
        mine = session.scalar(select(BattleVote.choice).where(BattleVote.battle_id == battle_id, BattleVote.voter_id == voter_id))
    counts = {choice: count for choice, count in rows}
    return {"counts": counts, "total": sum(counts.values()), "your_vote": mine}


def _latest_scorecard(session, lyrics: Asset) -> Asset | None:
    """Newest scorecard for this battle (scorecards are few; filtered in Python)."""
    cards = session.scalars(
        select(Asset).where(Asset.kind == AssetKind.SCORECARD, Asset.project_id == lyrics.project_id).order_by(Asset.created_at.desc())
    )
    return next((card for card in cards if (card.meta or {}).get("battle_id") == lyrics.root_id), None)


@router.get("/{asset_id}")
def get_battle(asset_id: str, session: SessionDep, voter_id: str | None = None):
    """Everything the battle page shows: rappers, lyrics, latest scorecard and votes."""
    lyrics = _lyrics_of(session, load_asset(session, asset_id))
    a, b = _rappers(lyrics)
    card = _latest_scorecard(session, lyrics)
    return {
        "battle_id": lyrics.root_id,
        "rappers": [a, b],
        "lyrics": AssetOut.model_validate(lyrics),
        "scorecard": AssetOut.model_validate(card) if card else None,
        "votes": _tally(session, lyrics.root_id, voter_id),
    }


@router.post("/{asset_id}/score", response_model=AssetOut, status_code=201)
def score_battle(asset_id: str, session: SessionDep, providers: ProvidersDep):
    """Ask the text model to judge the battle. Stored as a ``scorecard`` asset
    that says it is an AI opinion. Scoring again adds a new scorecard."""
    provider = providers.require("text")
    lyrics = _lyrics_of(session, load_asset(session, asset_id))
    a, b = _rappers(lyrics)
    service = LyricsService(provider, json_mode=providers.json_mode())  # type: ignore[arg-type]
    card = asyncio.run(service.score_battle(Lyrics.model_validate(lyrics.content), a, b))
    meta = card.meta
    content = card.model_dump(mode="json", exclude={"meta"})
    content["overall"] = {name: score.overall for name, score in card.scores.items()}
    asset = create_asset(
        session, kind=AssetKind.SCORECARD, title=f"{a} vs {b} · judges' scorecard", project_id=lyrics.project_id,
        content=content, provider=meta.provider if meta else None, model=meta.model if meta else None,
        is_mock=bool(meta and meta.is_mock), is_ai=not (meta and meta.is_mock), origin="generated",
    )
    asset.meta = {"battle_id": lyrics.root_id, "opinion": True}
    session.add(AssetLink(asset_id=asset.id, source_asset_id=lyrics.id, relation="lyrics"))
    session.commit()
    return asset


@router.get("/{asset_id}/votes")
def votes(asset_id: str, session: SessionDep, voter_id: str | None = None):
    lyrics = _lyrics_of(session, load_asset(session, asset_id))
    return _tally(session, lyrics.root_id, voter_id)


@router.post("/{asset_id}/votes")
def vote(asset_id: str, body: VoteBody, session: SessionDep):
    """Vote for a rapper (or a draw). Voting again with the same ``voter_id`` changes the vote."""
    lyrics = _lyrics_of(session, load_asset(session, asset_id))
    allowed = {*_rappers(lyrics), "draw"}
    if body.choice not in allowed:
        raise ApiError(422, "validation_error", f"Vote for one of: {', '.join(sorted(allowed))}.")
    existing = session.scalar(select(BattleVote).where(BattleVote.battle_id == lyrics.root_id, BattleVote.voter_id == body.voter_id))
    if existing:
        existing.choice = body.choice
    else:
        session.add(BattleVote(battle_id=lyrics.root_id, voter_id=body.voter_id, choice=body.choice))
    session.commit()
    return _tally(session, lyrics.root_id, body.voter_id)
