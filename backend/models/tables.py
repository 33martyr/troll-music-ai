"""Database schema.

``assets`` is one table for every kind of creative output. Text assets
(lyrics, storyboards) live in ``content``; binary assets (audio, video, images)
live in object storage under ``storage_key``.

Two kinds of relationship are tracked:

* **Versions**: ``parent_id`` / ``root_id`` / ``version``. Editing or
  regenerating an asset never overwrites it; it adds a version.
* **Provenance**: ``asset_links`` records which assets another asset was made
  from (a song from lyrics + beat + vocals), so one component can be
  regenerated without touching the others.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.db import Base


def new_id() -> str:
    return uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssetKind:
    LYRICS = "lyrics"
    BEAT = "beat"
    VOCALS = "vocals"
    SONG = "song"
    VIDEO = "video"
    ARTWORK = "artwork"
    STORYBOARD = "storyboard"
    ALL = (LYRICS, BEAT, VOCALS, SONG, VIDEO, ARTWORK, STORYBOARD)


class JobStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ACTIVE = (QUEUED, PROCESSING)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    assets: Mapped[list["Asset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    # NULL project = the user's unsorted library.
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(200))

    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # bpm, dimensions, timings, ...
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # the generation request

    provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ai: Mapped[bool] = mapped_column(Boolean, default=True)  # False = built-in engine or upload
    origin: Mapped[str] = mapped_column(String(30), default="generated")

    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    root_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project | None] = relationship(back_populates="assets")


class AssetLink(Base):
    """Provenance edge: ``asset_id`` was made from ``source_asset_id``."""

    __tablename__ = "asset_links"

    asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    source_asset_id: Mapped[str] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(String(30), primary_key=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.QUEUED, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str] = mapped_column(String(120), default="Queued")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result_asset_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # primary output
    result_asset_ids: Mapped[list] = mapped_column(JSON, default=list)  # every output
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project | None] = relationship(back_populates="jobs")


class VoiceProfile(Base):
    """An authorized voice. A row cannot exist without recorded consent, and the
    sample is kept in private storage under ``sample_storage_key``."""

    __tablename__ = "voice_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    owner_name: Mapped[str] = mapped_column(String(120))
    consent_statement: Mapped[str] = mapped_column(Text)
    consent_given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sample_storage_key: Mapped[str] = mapped_column(String(400))
    provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    provider_voice_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # sample analysis
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderSetting(Base):
    """Provider choice made in Model Settings. Overrides the environment.

    ``api_key`` is stored so the backend can call the provider. It is never
    returned by the API.
    """

    __tablename__ = "provider_settings"

    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    provider: Mapped[str] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
