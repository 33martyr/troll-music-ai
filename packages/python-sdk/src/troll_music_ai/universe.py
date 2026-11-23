"""Troll Universe: fictional rapper identities, and Roast Awards.

A rapper profile is plain data. An AI text model can invent one from an idea
(:func:`profile_messages` / :func:`parse_profile`); without a model,
:func:`random_profile` builds one from word lists and says so. Awards are an
AI model's opinion of a track, picked from a fixed list.
"""

from __future__ import annotations

import random

from pydantic import BaseModel, Field, field_validator

from .errors import LyricsParseError
from .lyrics.parser import extract_json
from .providers.base import ChatMessage
from .troll import DELIVERIES, STYLES, rapper_name

STAT_NAMES = ("punchline", "flow", "comedy", "creativity", "reputation")


class RapperStats(BaseModel):
    """1-99, like a trading card. Invented for fun, not measured."""

    punchline: int = Field(default=50, ge=1, le=99)
    flow: int = Field(default=50, ge=1, le=99)
    comedy: int = Field(default=50, ge=1, le=99)
    creativity: int = Field(default=50, ge=1, le=99)
    reputation: int = Field(default=50, ge=1, le=99)

    @property
    def overall(self) -> int:
        return round(sum(getattr(self, name) for name in STAT_NAMES) / len(STAT_NAMES))


class RapperProfile(BaseModel):
    """A fictional rapper. Never a real person."""

    name: str = Field(min_length=1, max_length=40)
    personality: str = Field(default="", max_length=300)
    style: str = Field(default="trap", description="One of troll.STYLES (song styles).")
    delivery: str = Field(default="cocky", description="One of troll.DELIVERIES.")
    catchphrase: str = Field(default="", max_length=120)
    bio: str = Field(default="", max_length=800)
    stats: RapperStats = Field(default_factory=RapperStats)
    voice: str | None = Field(default=None, max_length=120)

    @field_validator("style")
    @classmethod
    def _style(cls, value: str) -> str:
        return value if value in STYLES else "trap"

    @field_validator("delivery")
    @classmethod
    def _delivery(cls, value: str) -> str:
        return value if value in DELIVERIES else "cocky"


_SYSTEM = (
    "You invent fictional comedy rappers for a party game. Never base one on a real person or real artist, "
    "never use real artists' names, and keep everything family-friendly and funny. Reply with one JSON object only."
)


def profile_messages(idea: str | None) -> list[ChatMessage]:
    styles = ", ".join(k for k in STYLES if k not in ("circus", "8-bit"))
    deliveries = ", ".join(DELIVERIES)
    user = f"""\
TASK: create_rapper
IDEA: {idea or "surprise me"}

Invent one original, ridiculous fictional rapper from the idea. Give a funny stage name (max 3 words), a \
one-sentence personality, a 3-sentence biography with an absurd origin story, a short catchphrase, a style \
from [{styles}], a delivery from [{deliveries}], and stats from 1 to 99 for punchline, flow, comedy, \
creativity and reputation that fit the character (they should not all be high).

Return JSON in this shape:
{{"name": "...", "personality": "...", "bio": "...", "catchphrase": "...", "style": "trap", "delivery": "cocky", \
"stats": {{"punchline": 70, "flow": 55, "comedy": 88, "creativity": 64, "reputation": 30}}}}"""
    return [ChatMessage(role="system", content=_SYSTEM), ChatMessage(role="user", content=user)]


def parse_profile(text: str) -> RapperProfile:
    data = extract_json(text)
    name = " ".join(str(data.get("name") or "").split())[:40]
    if not name:
        raise LyricsParseError("The model did not name the rapper.")
    raw_stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    stats = {}
    for stat in STAT_NAMES:
        try:
            stats[stat] = max(1, min(99, round(float(raw_stats.get(stat, 50)))))
        except (TypeError, ValueError):
            stats[stat] = 50
    return RapperProfile(
        name=name,
        personality=str(data.get("personality") or "")[:300],
        bio=str(data.get("bio") or "")[:800],
        catchphrase=str(data.get("catchphrase") or "")[:120],
        style=str(data.get("style") or "trap"),
        delivery=str(data.get("delivery") or "cocky"),
        stats=RapperStats(**stats),
    )


_ORIGINS = (
    "raised by a pack of feral group chats", "discovered rapping to a microwave countdown",
    "born in the queue for a sold-out sneaker drop", "trained in an abandoned karaoke bar",
    "lost a rap battle to a parking meter and swore revenge", "signed to a label that turned out to be a car wash",
)
_PERSONALITIES = (
    "thinks every bar is a classic", "apologises after every punchline", "only raps about snacks",
    "treats every beef like a courtroom drama", "has never finished a verse on time", "flexes things nobody asked about",
)
_CATCHPHRASES = ("Receipt printed.", "Check the replay.", "Emotional damage, delivered.", "Skill issue.", "Mic: dropped. Ego: intact.")


def random_profile(idea: str | None = None, *, seed: int | None = None) -> RapperProfile:
    """A profile from word lists. Used when no text model is configured; the
    caller must label it as not AI-written."""
    rng = random.Random(seed)
    name = rapper_name(seed=rng.randrange(2**31))
    origin = rng.choice(_ORIGINS)
    personality = rng.choice(_PERSONALITIES)
    return RapperProfile(
        name=name,
        personality=f"{name} {personality}." if not idea else f"{idea.strip()[:200]}",
        bio=f"{name} was {origin}. Nobody asked for a debut album; one arrived anyway. Critics called it 'audible'.",
        catchphrase=rng.choice(_CATCHPHRASES),
        style=rng.choice([s for s in STYLES if s not in ("circus", "8-bit")]),
        delivery=rng.choice(list(DELIVERIES)),
        stats=RapperStats(**{stat: rng.randint(20, 95) for stat in STAT_NAMES}),
    )


# --------------------------------- awards ---------------------------------- #

AWARDS: tuple[str, ...] = (
    "Best Punchline", "Most Emotional Damage", "Funniest Chorus", "Best Flow", "Most Creative Diss",
    "Worst Friend of the Year", "Most Likely to End a Friendship", "Legendary Roast",
)


class Award(BaseModel):
    award: str
    reason: str
    line: str | None = None


def awards_messages(lyrics_json: str, count: int = 3) -> list[ChatMessage]:
    user = f"""\
TASK: roast_awards
COUNT: {count}

Here is a comedy track:
<song>
{lyrics_json}
</song>

You host "The Trollies", a fake award show for roast songs. Give this track {count} different awards chosen \
ONLY from this list: {", ".join(AWARDS)}. For each, write a one-sentence funny reason that points at a \
specific line, and quote that line exactly.

Return JSON in this shape:
{{"awards": [{{"award": "Best Punchline", "reason": "...", "line": "..."}}]}}"""
    return [ChatMessage(role="system", content=_SYSTEM.replace("invent fictional comedy rappers for a party game", "judge comedy songs for a party game")), ChatMessage(role="user", content=user)]


def parse_awards(text: str, count: int = 3) -> list[Award]:
    raw = extract_json(text).get("awards")
    if not isinstance(raw, list):
        raise LyricsParseError("The model gave no awards.")
    by_lower = {a.lower(): a for a in AWARDS}
    found: list[Award] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = by_lower.get(str(item.get("award") or "").strip().lower())
        reason = " ".join(str(item.get("reason") or "").split())[:300]
        if name and reason and name not in {a.award for a in found}:
            line = " ".join(str(item.get("line") or "").split())[:200] or None
            found.append(Award(award=name, reason=reason, line=line))
    if not found:
        raise LyricsParseError("None of the model's awards were on the list.")
    return found[:count]
