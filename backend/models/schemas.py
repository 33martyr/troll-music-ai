"""Request and response models for the REST API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field

from backend.core import security
from troll_music_ai.types import BattleRequest, BeatRequest, LyricsRequest, RewriteMode, SectionType
from troll_music_ai.troll import TrollRequest


def _as_utc(value: datetime) -> datetime:
    # SQLite drops timezone info; everything is stored in UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------ projects ---------------------------------- #


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectOut(OrmModel):
    id: str
    name: str
    description: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    asset_counts: dict[str, int] = Field(default_factory=dict)


# ------------------------------- assets ----------------------------------- #


class AssetOut(OrmModel):
    id: str
    project_id: str | None
    kind: str
    title: str
    content: dict[str, Any] | None
    params: dict[str, Any] | None
    meta: dict[str, Any] | None
    mime_type: str | None
    size_bytes: int | None
    duration_seconds: float | None
    provider: str | None
    model: str | None
    is_mock: bool
    is_ai: bool
    origin: str
    parent_id: str | None
    root_id: str
    version: int
    is_latest: bool
    approved: bool
    created_at: UtcDatetime
    # Where the file lives is internal; clients fetch /api/assets/{id}/file.
    storage_key: str | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def has_file(self) -> bool:
        return bool(self.storage_key)

    @computed_field
    @property
    def file_token(self) -> str | None:
        """Signature for ``?token=`` on the file URL when an API key is set."""
        return security.file_token(self.id) if self.storage_key else None


class AssetUpdate(BaseModel):
    approved: bool | None = None
    project_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)


# -------------------------------- jobs ------------------------------------ #


class JobOut(OrmModel):
    id: str
    project_id: str | None
    kind: str
    status: str
    progress: float
    stage: str
    provider: str | None
    model: str | None
    result_asset_id: str | None
    result_asset_ids: list[str] = Field(default_factory=list)
    retry_of: str | None
    error_code: str | None
    error: str | None
    created_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None


# ------------------------------- lyrics ----------------------------------- #


class GenerateLyricsBody(BaseModel):
    project_id: str | None = None
    request: LyricsRequest


class ImportLyricsBody(BaseModel):
    project_id: str | None = None
    title: str = Field(default="Untitled", min_length=1, max_length=120)
    text: str = Field(min_length=3, max_length=20000)
    language: str = Field(default="English", max_length=40)


class RegenerateSectionBody(BaseModel):
    section_id: str
    instruction: str | None = Field(default=None, max_length=500)


class PunchlinesBody(BaseModel):
    section_id: str
    line_index: int = Field(ge=0, le=200)
    count: int = Field(default=5, ge=2, le=8)
    instruction: str | None = Field(default=None, max_length=300)


class RewriteLyricsBody(BaseModel):
    mode: RewriteMode
    instruction: str | None = Field(default=None, max_length=500)
    rhyme_scheme: str | None = Field(default=None, max_length=20)


class SectionEdit(BaseModel):
    id: str | None = None
    type: SectionType
    label: str = Field(min_length=1, max_length=60)
    lines: list[str]


class SaveLyricsBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    sections: list[SectionEdit] = Field(min_length=1)


class GenerateBattleBody(BaseModel):
    project_id: str | None = None
    request: BattleRequest


class SuggestCharactersBody(BaseModel):
    topic: str = Field(min_length=3, max_length=1000)


# ------------------------------- studio ----------------------------------- #


class GenerateBeatBody(BaseModel):
    project_id: str | None = None
    lyrics_asset_id: str | None = None  # recorded as provenance only
    request: BeatRequest


class GenerateVocalsBody(BaseModel):
    project_id: str | None = None
    lyrics_asset_id: str
    beat_asset_id: str | None = None  # used for its tempo
    bpm: float | None = Field(default=None, ge=50, le=220)
    voice: str | None = Field(default=None, max_length=200)
    voice_b: str | None = Field(default=None, max_length=200)  # second performer in a battle
    voice_profile_id: str | None = None


class ConvertVocalsBody(BaseModel):
    project_id: str | None = None
    source_asset_id: str
    voice_profile_id: str


class GenerateSongBody(BaseModel):
    project_id: str | None = None
    # "mix" lays vocals over a beat. "model" asks a singing music model for the whole song.
    mode: Literal["mix", "model"] = "mix"
    lyrics_asset_id: str
    beat_asset_id: str | None = None
    vocals_asset_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    voice: str | None = Field(default=None, max_length=200)
    voice_b: str | None = Field(default=None, max_length=200)
    voice_profile_id: str | None = None
    vocal_gain_db: float = Field(default=3.0, ge=-12, le=12)
    beat_gain_db: float = Field(default=-4.0, ge=-18, le=6)
    style_prompt: str | None = Field(default=None, max_length=500)  # model mode
    duration_seconds: float | None = Field(default=None, ge=10, le=300)  # model mode


class VideoIntro(BaseModel):
    """A dramatic opening title card: '<presenter> PRESENTS <title>'."""

    presenter: str = Field(min_length=1, max_length=40)
    title: str | None = Field(default=None, max_length=120)


class GenerateVideoBody(BaseModel):
    project_id: str | None = None
    audio_asset_id: str | None = None
    lyrics_asset_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    style: str = Field(default="lyric video", max_length=60)
    aspect: Literal["16:9", "9:16", "1:1"] = "16:9"
    subtitles: bool = True
    duration_seconds: float | None = Field(default=None, ge=3, le=600)  # only without audio
    notes: str | None = Field(default=None, max_length=500)
    intro: VideoIntro | None = None


class GenerateArtworkBody(BaseModel):
    project_id: str | None = None
    lyrics_asset_id: str | None = None
    title: str = Field(min_length=1, max_length=120)
    genre: str = Field(default="hip-hop", max_length=60)
    mood: str | None = Field(default=None, max_length=60)
    style: str = Field(default="cartoon", max_length=60)
    character: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=500)
    # Set to turn the picture into a fake album cover: artist, title and a parody sticker.
    artist: str | None = Field(default=None, max_length=40)


class RemixBody(BaseModel):
    """Redo a finished troll with different settings, reusing what did not change."""

    asset_id: str = Field(description="The troll's song, beat or video.")
    style: str | None = None
    intensity: str | None = None
    delivery: str | None = None
    rapper_name: str | None = Field(default=None, max_length=40)
    voice: str | None = Field(default=None, max_length=120)
    instruction: str | None = Field(default=None, max_length=500, description="Rewrite the lyrics this way first.")
    regenerate_sections: list[str] = Field(default_factory=list, max_length=12, description="Section ids to rewrite; the rest is kept.")
    section_instruction: str | None = Field(default=None, max_length=300, description="How to rewrite those sections.")
    with_video: bool = False
    with_cover: bool = True


class FactoryBody(BaseModel):
    """Meme Factory: shareable formats from a finished troll."""

    asset_id: str = Field(description="The troll's song (or beat).")
    items: list[Literal[
        "vertical_video", "square_video", "wide_video", "square_cover",
        "concert_poster", "award_card", "streaming_card", "reaction_meme",
    ]] = Field(min_length=1, max_length=8)
    theme: Literal["neon", "gold", "vaporwave", "grunge", "comic"] = "neon"
    award: str | None = Field(default=None, max_length=60)
    line: str | None = Field(default=None, max_length=200, description="The lyric to feature; the chorus by default.")


class ZipBody(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=50)
    name: str = Field(default="troll-music-ai", max_length=80)


class TrollBody(BaseModel):
    """One button: the whole meme, from the situation to the shareable file."""

    request: TrollRequest
    project_id: str | None = None
    # Meme video and funny beat always render their own extras; these add them to the rest.
    with_video: bool = False
    with_cover: bool = True


# ------------------------------- voices ----------------------------------- #


class VoiceProfileOut(OrmModel):
    id: str
    name: str
    owner_name: str
    consent_statement: str
    consent_given_at: UtcDatetime
    provider: str | None
    meta: dict[str, Any] | None
    created_at: UtcDatetime
    provider_voice_id: str | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def usable(self) -> bool:
        """True when a cloning provider has registered this voice."""
        return bool(self.provider and self.provider_voice_id)

    @computed_field
    @property
    def sample_token(self) -> str | None:
        return security.file_token(self.id)


class StockVoicesOut(BaseModel):
    provider: str | None
    model: str | None = None
    is_ai: bool = False
    voices: list[str] = Field(default_factory=list)
    speech: bool = False
    singing: bool = False
    cloning: bool = False
    conversion: bool = False
    note: str = ""


# ------------------------------- system ----------------------------------- #


class CapabilityOut(BaseModel):
    kind: str
    label: str
    implemented: bool
    configured: bool
    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None
    is_mock: bool = False
    is_ai: bool = True
    # Music only: the provider sings whole songs from lyrics (not text-to-speech).
    sings: bool = False
    note: str = ""


class ProviderCheckOut(BaseModel):
    ok: bool
    detail: str
    models: list[str] = Field(default_factory=list)


class ProviderOptionOut(BaseModel):
    name: str
    label: str
    description: str
    local: bool
    is_ai: bool
    is_mock: bool
    needs_api_key: bool
    needs_base_url: bool
    needs_model: bool
    default_base_url: str | None
    default_model: str | None
    suggested_models: list[str]
    capabilities: list[str]
    params: list[str]
    hardware: str
    license: str
    commercial_use: bool | None
    setup: str
    verified: bool
    missing_packages: list[str]


class ProviderStateOut(BaseModel):
    kind: str
    label: str
    source: str  # environment | settings | override
    provider: str  # "none" when nothing is selected
    model: str | None
    base_url: str | None
    has_api_key: bool  # the key itself is never returned
    enabled: bool
    configured: bool
    error: str = ""
    is_ai: bool = False
    is_mock: bool = False
    options: list[ProviderOptionOut]


class ProviderUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=60)
    model: str | None = Field(default=None, max_length=200)
    base_url: str | None = Field(default=None, max_length=400)
    # Omit to keep the stored key; send "" to clear it.
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True
