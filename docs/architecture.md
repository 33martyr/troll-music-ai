# Architecture

## Overview

```
┌──────────────┐  REST   ┌─────────────────────────────┐        ┌──────────────────┐
│  apps/web    │ ──────▶ │  backend (FastAPI)          │ ─────▶ │  troll_music_ai  │
│  Next.js     │ ◀────── │  api → services → workers   │        │  Python toolkit  │
└──────────────┘  JSON   │  SQLAlchemy models          │        │  types           │
                         └──────────────┬──────────────┘        │  provider ifaces │
                                        │                       │  provider adapters│
                              ┌─────────┴─────────┐             │  lyrics service  │
                              │ SQLite / Postgres │             └────────┬─────────┘
                              │ file storage      │                      │ HTTP / local
                              │ FFmpeg            │       Pollinations, Ollama, MusicGen, ACE-Step,
                              └───────────────────┘       ElevenLabs, OS speech, ComfyUI, ...
```

Media processing (FFmpeg) lives in the backend (`backend/audio`, `backend/video`); the toolkit's providers
only write raw output files.

Three layers, with dependencies pointing one way:

1. **Toolkit** (`packages/python-sdk`). All generation logic, typed inputs and outputs, provider interfaces
   and adapters. Depends on `pydantic` and `httpx` only. Knows nothing about HTTP servers, databases or the
   web app.
2. **Backend** (`backend/`). Persistence, projects, version history, background jobs and the REST API. It
   calls the toolkit; it contains no prompt or model logic of its own.
3. **Web app** (`apps/web`). A client of the REST API. It holds no secrets and no business rules.

Because the toolkit is the single home of generation logic, the SDK and the studio cannot drift apart.

## Independent modules

Each generator is a separate module with its own service, endpoints and page. Modules communicate through
saved **assets**, never by calling each other. A song is built from a lyrics asset, a beat asset and a
vocals asset that already exist, which is what makes "regenerate the beat but keep my approved lyrics"
possible. The studio pages chain modules with links ("Make a beat for it", "Use in a song", "Make a
video"), always passing asset ids, never regenerating a source.

## Database schema

Defined in [`backend/models/tables.py`](../backend/models/tables.py). SQLite by default; PostgreSQL through
`TROLL_DATABASE_URL`.

### `projects`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string(32) PK | UUID hex |
| `name`, `description` | string, text | |
| `created_at`, `updated_at` | timestamptz | `updated_at` is bumped when an asset is added |

### `assets`

One table for every kind of output.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string(32) PK | |
| `project_id` | FK → projects, nullable | `NULL` = the unsorted library |
| `kind` | string | `lyrics`, `beat`, `vocals`, `song`, `video`, `artwork`, `storyboard` |
| `title` | string | |
| `content` | JSON, nullable | Structured content for text assets (lyrics, storyboards) |
| `storage_key`, `mime_type`, `size_bytes`, `duration_seconds` | nullable | The media file in storage |
| `meta` | JSON, nullable | Media facts: bpm, `bpm_exact`, `looped`, `delivery`, `line_timings`, dimensions, renderer |
| `params` | JSON, nullable | The request that produced the asset |
| `provider`, `model`, `is_mock`, `is_ai` | | Provenance. `is_ai` is false for built-in engines and uploads |
| `origin` | string | `generated`, `edited`, `section_regenerated`, `rewritten`, `imported`, `uploaded`, `battle`, `converted` |
| `parent_id`, `root_id`, `version`, `is_latest` | | Version lineage, see below |
| `approved` | bool | User sign-off; approved assets are never regenerated implicitly |
| `created_at` | timestamptz | |

**Versions.** Assets are immutable. Editing or regenerating creates a new row whose `parent_id` points at
the version it came from; all versions share a `root_id`, and exactly one has `is_latest = true`. Listings
show the latest version; `GET /api/assets/{id}/history` returns the lineage.

### `asset_links`

Provenance between different assets: `(asset_id, source_asset_id, relation)`. For example a song links to
its lyrics, beat and vocals; a video to its audio, lyrics and storyboard.

### `jobs`

| Column | Notes |
| --- | --- |
| `id`, `project_id`, `kind` | `kind` selects the handler: `lyrics.*`, `battle.generate`, `beat.generate`, `vocals.generate`, `vocals.convert`, `song.generate`, `video.generate`, `artwork.generate` |
| `status` | `queued` → `processing` → `completed`, `failed` or `cancelled` |
| `progress`, `stage` | 0 to 1 and a short human-readable stage |
| `provider`, `model` | What actually ran |
| `params` | JSON input for the handler |
| `result_asset_id`, `result_asset_ids` | Primary output and every output |
| `cancel_requested`, `retry_of` | Cancellation flag; the job this one retries |
| `error_code`, `error` | Set on failure; safe to show to users |

### `voice_profiles`

A row cannot exist without `owner_name`, `consent_statement` and `consent_given_at`. The sample is a
private WAV under `sample_storage_key`; `provider` and `provider_voice_id` are set when a cloning provider
registered the voice. `meta` holds the sample analysis.

### `provider_settings`

One row per capability chosen in Model Settings: `provider`, `model`, `base_url`, `api_key` (never returned
by the API), `enabled`. Overrides the environment.

Migrations: tables are created with `create_all` on startup, which does **not** add columns to existing
tables. A database created by version 0.1 must be deleted (or migrated by hand) for 0.2. Alembic is on the
roadmap.

## Provider interfaces

Defined in [`providers/base.py`](../packages/python-sdk/src/troll_music_ai/providers/base.py).

| Interface | Methods | Adapters |
| --- | --- | --- |
| `TextGenerationProvider` | `generate_text` | OpenAI-compatible (ollama, openai, pollinations, generic), mock |
| `MusicGenerationProvider` | `generate_instrumental`, `generate_song`, `capabilities` (exact_bpm, max_duration, with_vocals) | procedural, musicgen, acestep, elevenlabs_music |
| `VoiceProvider` | `voices`, `synthesize_lines`, `create_voice`, `delete_voice`, `convert_voice`, `capabilities` (speech, singing, cloning, conversion) | system_tts, openai_speech, elevenlabs, chatterbox |
| `ImageGenerationProvider` | `generate_image` | typographic, pollinations, openai_images, comfyui |
| `VideoGenerationProvider` | `animate` | none (the FFmpeg renderer is used) |

Every provider exposes `info` (name, model, endpoint, `is_mock`, `is_ai`) and `check()`, a probe that never
raises. The **registry** (`providers/registry.py`) describes each one with a `ProviderSpec`: local or hosted,
needs (key, URL, model), defaults, suggested models, honoured params, hardware, licence, required packages,
setup and `verified`. `registry.build()` refuses incomplete configuration loudly. In the backend,
`ProviderManager` resolves test override → Model Settings → environment and caches built providers.

## Media pipeline

- **Beats**: provider → `finalize_audio` (loop when the provider's max length is shorter, trim, fade,
  loudnorm −14 LUFS, MP3 192k).
- **Vocals**: one speech file per line → silence-trimmed → placed on the bar grid (≤1.35× speed-up, longer
  lines take 2 or 4 bars, sections start on even bars, two-bar lead-in) → `line_timings`.
- **Songs**: beat looped under the vocals, vocal high-pass and compression, `amix`, loudnorm, two-bar outro.
- **Videos**: scenes cut at section boundaries (from `line_timings` when present, max 10 s each, max 24) →
  one image each → Ken Burns zoom and fades per clip → concat → audio → ASS subtitles burned in → H.264/AAC.

FFmpeg comes from `PATH`, `TROLL_FFMPEG_PATH`, or the binary bundled with `imageio-ffmpeg`.

Design decisions worth knowing:

- **Lyrics are not a provider.** `LyricsService` is built on `TextGenerationProvider`, so any chat model can
  write lyrics. Storyboards and scene descriptions will reuse the same interface.
- **Singing is not speech.** `SingingVoiceProvider` and `SpeechProvider` are separate on purpose. A cloned
  text-to-speech voice cannot be assumed to sing in time and in key.
- **Video is optional.** The video pipeline must work with images, transitions and captions when no
  `VideoGenerationProvider` is configured.
- **Mock providers are for tests.** They set `is_mock`, which is stored on every asset they produce and
  shown in the UI and in exports.

Errors are typed (`ProviderNotConfiguredError`, `ProviderUnavailableError`, `ProviderResponseError`,
`LyricsParseError`, `FeatureNotAvailableError`), each with a stable `code` that the API passes through.

## Jobs

Generation never runs inside an HTTP handler:

1. The endpoint validates input, inserts a `jobs` row and enqueues its id, then returns `202` with the job.
2. A worker runs the handler registered for `job.kind`, reporting progress as it goes.
3. The handler stores its result as an asset and the job records `result_asset_id`.
4. The client polls `GET /api/jobs/{id}`.

`JobQueue` is an interface with two implementations: `ThreadPoolJobQueue` (in-process, the default) and
`InlineJobQueue` (tests). The in-process queue keeps the first install free of Redis, with one honest
limitation: jobs do not survive a restart, so unfinished jobs are marked `failed` with code `interrupted`
on startup. A Redis-backed worker only has to implement `enqueue`.

Each job gets a temporary work directory, removed afterwards. Cancellation is checked at every progress
step. On failure, files of rolled-back assets are deleted; outputs already committed are kept and listed.

## Storage

Text assets live in the database. Media files live under `TROLL_STORAGE_DIR` (`LocalStorage`, behind a
`Storage` protocol so an S3 backend can be added). Files are served only through `/api/assets/{id}/file`
(range requests supported) and `/api/voices/{id}/sample`, behind the same auth as the rest of the API.
Deleting an asset, a project or a voice profile deletes its files; duplicating a project copies them.

## Configuration and secrets

Configuration is `TROLL_*` environment variables, plus Model Settings stored in the database. Keys are held
as `SecretStr` or in `provider_settings.api_key`, never returned by any endpoint (only `has_api_key`), and
not included in error messages. The web app only knows the backend URL and, if auth is on, the studio key
the user typed in.

## Known limitations

- Single tenant: no user accounts. Use `TROLL_API_KEY` if the API is reachable by others.
- No Alembic migrations; the job queue is in-process; storage is local disk.
- No AI video animation; no singing voice from a user's own voice.
- Several adapters are untested against the real service; see [models.md](models.md).
