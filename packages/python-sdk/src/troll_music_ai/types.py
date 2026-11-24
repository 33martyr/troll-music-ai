"""Typed inputs and outputs shared by the toolkit, the REST API and the web app."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #


class LyricStyle(StrEnum):
    TROLL = "troll"
    SAVAGE = "savage"
    SARCASTIC = "sarcastic"
    FUNNY = "funny"
    ABSURD = "absurd"
    DARK_COMEDY = "dark_comedy"
    SATIRICAL = "satirical"
    DISS_TRACK = "diss_track"
    MEME_RAP = "meme_rap"
    STORYTELLING = "storytelling"
    PARODY = "parody"


class SongLength(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class RhymeComplexity(StrEnum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ChorusStyle(StrEnum):
    CATCHY = "catchy"
    CHANT = "chant"
    MELODIC = "melodic"
    CALL_AND_RESPONSE = "call_and_response"
    MINIMAL = "minimal"


class SectionType(StrEnum):
    INTRO = "intro"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    OUTRO = "outro"


class RewriteMode(StrEnum):
    FUNNIER = "funnier"
    MORE_SAVAGE = "more_savage"
    RHYME_SCHEME = "rhyme_scheme"
    CUSTOM = "custom"


# Suggestions only: `genre` and `mood` are free text so callers are not boxed in.
GENRES: tuple[str, ...] = (
    "trap", "drill", "hip-hop", "phonk", "afrobeats", "reggaeton", "edm",
    "boom bap", "lo-fi", "pop", "rock", "jazz", "experimental",
)
MOODS: tuple[str, ...] = (
    "playful", "aggressive comedy", "smug", "petty", "chaotic", "deadpan",
    "triumphant", "melancholic", "hype",
)
RHYME_SCHEMES: tuple[str, ...] = ("AABB", "ABAB", "ABBA", "AAAA", "ABCB")


# --------------------------------------------------------------------------- #
# Lyrics
# --------------------------------------------------------------------------- #


def _new_id() -> str:
    return uuid4().hex[:8]


class LyricsRequest(BaseModel):
    """Everything a user can specify when asking for lyrics."""

    prompt: str = Field(min_length=3, max_length=2000, description="What the song is about.")
    genre: str = Field(default="trap", max_length=60)
    mood: str = Field(default="playful", max_length=60)
    language: str = Field(default="English", max_length=40)
    style: LyricStyle = LyricStyle.TROLL
    troll_intensity: int = Field(default=3, ge=1, le=5)
    explicit: bool = False
    length: SongLength = SongLength.MEDIUM
    verses: int = Field(default=2, ge=1, le=4)
    chorus_style: ChorusStyle = ChorusStyle.CATCHY
    rhyme_complexity: RhymeComplexity = RhymeComplexity.MODERATE
    include_bridge: bool = False
    persona: str | None = Field(
        default=None,
        max_length=200,
        description="Optional fictional artist or character voice.",
    )

    @field_validator("prompt", "genre", "mood", "language")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("persona")
    @classmethod
    def _blank_persona(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None


class LyricSection(BaseModel):
    id: str = Field(default_factory=_new_id)
    type: SectionType
    label: str
    lines: list[str]
    performer: str | None = None  # rap battles: which character delivers this section


class GenerationMeta(BaseModel):
    """Where an asset came from. ``is_mock`` must be surfaced to end users."""

    provider: str
    model: str | None = None
    is_mock: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Lyrics(BaseModel):
    title: str
    sections: list[LyricSection]
    suggested_bpm: int | None = None
    suggested_genre: str | None = None
    beat_notes: list[str] = Field(default_factory=list)
    language: str = "English"
    explicit: bool = False
    meta: GenerationMeta | None = None

    def section(self, section_id: str) -> LyricSection | None:
        return next((s for s in self.sections if s.id == section_id), None)

    def to_text(self) -> str:
        from .lyrics.export import to_text

        return to_text(self)

    def to_markdown(self) -> str:
        from .lyrics.export import to_markdown

        return to_markdown(self)


class BattleCharacter(BaseModel):
    """A fictional rapper. Not a real person."""

    name: str = Field(min_length=1, max_length=60)
    personality: str = Field(default="", max_length=300)
    style: str = Field(default="", max_length=120)


class BattleRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=1000, description="What the two are battling about.")
    character_a: BattleCharacter
    character_b: BattleCharacter
    rounds: int = Field(default=2, ge=1, le=4)
    genre: str = Field(default="boom bap", max_length=60)
    language: str = Field(default="English", max_length=40)
    troll_intensity: int = Field(default=3, ge=1, le=5)
    explicit: bool = False
    knockout: bool = Field(default=False, description="The last round is a Knockout round: each rapper's hardest verse.")


class BattleScore(BaseModel):
    """One rapper's marks from the AI judges: an opinion, not a measurement."""

    punchlines: int = Field(ge=1, le=10)
    flow: int = Field(ge=1, le=10)
    creativity: int = Field(ge=1, le=10)
    humor: int = Field(ge=1, le=10)
    entertainment: int = Field(ge=1, le=10)
    comment: str = ""

    @property
    def overall(self) -> float:
        return round((self.punchlines + self.flow + self.creativity + self.humor + self.entertainment) / 5, 1)


class Scorecard(BaseModel):
    scores: dict[str, BattleScore]
    winner: str | None  # None means the judges called a draw
    announcement: str
    best_line: str | None = None
    meta: GenerationMeta | None = None


# --------------------------------------------------------------------------- #
# Audio, voice and images
# --------------------------------------------------------------------------- #

INSTRUMENTS: tuple[str, ...] = (
    "808 bass", "piano", "synth lead", "strings", "guitar", "brass", "bells", "pads", "flute",
)
VISUAL_STYLES: tuple[str, ...] = (
    "meme", "cartoon", "cinematic", "anime-inspired", "surreal", "3d animation", "retro",
    "lyric video", "music montage",
)


class BeatRequest(BaseModel):
    genre: str = Field(default="trap", max_length=60)
    bpm: int | None = Field(default=None, ge=50, le=220)
    mood: str | None = Field(default=None, max_length=60)
    instruments: list[str] = Field(default_factory=list, max_length=8)
    energy: int = Field(default=3, ge=1, le=5)
    duration_seconds: float = Field(default=30, ge=5, le=300)
    key: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=500)
    variations: int = Field(default=1, ge=1, le=4)

    def prompt(self) -> str:
        """Text description for text-to-music models."""
        parts = [f"{self.genre} instrumental beat"]
        if self.mood:
            parts.append(f"{self.mood} mood")
        if self.bpm:
            parts.append(f"{self.bpm} BPM")
        if self.key:
            parts.append(f"in {self.key}")
        parts.append(["very calm", "laid back", "steady groove", "energetic", "intense, hard hitting"][self.energy - 1])
        if self.instruments:
            parts.append("with " + ", ".join(self.instruments))
        if self.description:
            parts.append(self.description.strip())
        return ", ".join(parts) + ", no vocals"


class SongPart(BaseModel):
    """One section of a song to be sung: its label and its lines, in order."""

    label: str = Field(min_length=1, max_length=100)
    lines: list[str] = Field(default_factory=list)


class SongRequest(BaseModel):
    """Full-song generation by a model that can sing (not speech synthesis).

    ``sections`` carries the same lyrics as ``lyrics_text`` in structured form,
    for models that take a per-section plan (ElevenLabs). ``style_prompt`` is a
    comma-separated list of musical and vocal directions.
    """

    lyrics_text: str
    style_prompt: str
    sections: list[SongPart] = Field(default_factory=list)
    negative_style: str | None = None
    duration_seconds: float = Field(default=90, ge=10, le=300)
    bpm: int | None = None
    language: str = "en"


class SpeechLine(BaseModel):
    text: str
    voice: str | None = None  # stock voice name, or a provider voice id for a cloned voice
    sample_path: str | None = None  # reference audio for zero-shot cloning providers


class VoiceConsent(BaseModel):
    """Explicit authorization from the owner of a voice. Required for cloning."""

    owner_name: str = Field(min_length=2, max_length=120)
    confirmed: bool
    statement: str = Field(min_length=10, max_length=1000)


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    seed: int = 0
    # Shown by the built-in typographic renderer; ignored by AI models.
    title: str | None = None
    subtitle: str | None = None
