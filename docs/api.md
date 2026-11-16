# REST API

Base URL: `http://localhost:8000`. Interactive documentation: `/docs` (OpenAPI at `/openapi.json`).

## Authentication

Off by default (single-user, local). Set `TROLL_API_KEY` and every route except `GET /api/health` requires
`Authorization: Bearer <key>`. Media routes (`/api/assets/{id}/file`, `/api/voices/{id}/sample`) also accept
`?token=` with the per-resource signature returned as `file_token` / `sample_token`, because `<audio>` and
`<video>` elements cannot send headers. A token opens only that one file. There are no user accounts: anyone
with the key sees everything, so do not expose the API publicly without it.

## Conventions

- JSON in and out, except uploads (multipart).
- Errors: `{ "error": { "code": "...", "message": "..." } }`

  | Status | Codes |
  | --- | --- |
  | 401 | `unauthorized` |
  | 404 | `not_found` |
  | 409 | `not_cancellable`, `not_retryable` |
  | 413 | `file_too_large` |
  | 422 | `validation_error`, `invalid_media`, `consent_required`, `provider_not_configured` (Model Settings) |
  | 501 | `feature_not_available` (e.g. a provider that cannot sing or clone) |
  | 502 | `provider_response_error`, `lyrics_parse_error` |
  | 503 | `provider_not_configured`, `provider_unavailable`, `ffmpeg_missing` |

- Generation endpoints validate inputs and the needed provider first, then answer `202` with a **job**.

## Jobs

`GET /api/jobs/{id}`:

```json
{ "id": "…", "kind": "beat.generate", "status": "processing", "progress": 0.42, "stage": "Generating variation 2 of 2 with procedural",
  "provider": "procedural", "model": "troll-synth-1", "result_asset_id": null, "result_asset_ids": [], "retry_of": null,
  "error_code": null, "error": null }
```

`status`: `queued` → `processing` → `completed` | `failed` | `cancelled`. `result_asset_id` is the primary
output; `result_asset_ids` lists every asset the job created (beat variations; a song's new vocal track).

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/jobs` | Newest first. `?active=true`, `?status=failed,cancelled`, `?project_id=` |
| POST | `/api/jobs/{id}/cancel` | Queued: cancelled at once. Processing: stops at the next step |
| POST | `/api/jobs/{id}/retry` | New job with the same input (`retry_of` points back) |

Jobs left running when the server stops are marked `failed` (`interrupted`) on the next start.

## Assets

Every output is an asset: `lyrics`, `beat`, `vocals`, `song`, `video`, `artwork`, `storyboard`.

Key fields: `kind`, `title`, `content` (lyrics/storyboard JSON), `meta` (bpm, `bpm_exact`, `looped`,
`delivery`, `line_timings`, width/height, renderer…), `mime_type`, `size_bytes`, `duration_seconds`,
`provider`, `model`, `is_mock`, `is_ai` (false for built-in engines and uploads), `origin`, `version`,
`has_file`, `file_token`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/assets` | Latest versions. `?kind=song,beat`, `?project_id=`, `?unsorted=true`, `?limit=` |
| GET | `/api/assets/{id}` | One version |
| GET | `/api/assets/{id}/history` | Every version |
| GET | `/api/assets/{id}/sources` | What it was made from: `[{relation, asset}]` |
| GET | `/api/assets/{id}/file` | The media file, with range support. `?download=1` for an attachment |
| PATCH | `/api/assets/{id}` | `approved`, `title`, `project_id` |
| DELETE | `/api/assets/{id}` | Delete all versions and their files |
| GET | `/api/assets/{id}/export?format=txt\|md` | Lyrics as text |
| POST | `/api/assets/upload` | Multipart: `file`, `kind` (beat\|vocals\|song), `title`, `project_id`, `bpm`. Checked with FFmpeg, stored as MP3 |

## Lyrics and battles

| Method | Path | Body |
| --- | --- | --- |
| POST | `/api/lyrics/generate` | `{ project_id, request: { prompt, genre, mood, language, style, troll_intensity, explicit, length, verses, chorus_style, rhyme_complexity, include_bridge, persona } }` |
| POST | `/api/lyrics/import` | `{ title, text, project_id }`. `[Verse 1]`-style headers mark sections. No model. Returns the asset (201) |
| POST | `/api/lyrics/{id}/regenerate-section` | `{ section_id, instruction }` |
| POST | `/api/lyrics/{id}/rewrite` | `{ mode: funnier\|more_savage\|rhyme_scheme\|custom, rhyme_scheme, instruction }` |
| PUT | `/api/lyrics/{id}` | Manual edit → new version |
| POST | `/api/battles/generate` | `{ project_id, request: { topic, character_a: {name, personality, style}, character_b, rounds, genre, language, troll_intensity, explicit } }` → lyrics whose sections carry `performer` |
| POST | `/api/battles/characters` | `{ topic }` → `{ characters: [...] }` (direct, not a job) |

## Beats, vocals, songs

| Method | Path | Body |
| --- | --- | --- |
| POST | `/api/beats/generate` | `{ project_id, lyrics_asset_id?, request: { genre, bpm, mood, instruments[], energy 1–5, duration_seconds 5–300, key, description, variations 1–4 } }` |
| POST | `/api/vocals/generate` | `{ lyrics_asset_id, beat_asset_id? or bpm?, voice?, voice_b? (battle performer B), voice_profile_id? }` |
| POST | `/api/vocals/convert` | `{ source_asset_id, voice_profile_id }` (provider must support conversion) |
| POST | `/api/songs/generate` | `{ mode: "mix", lyrics_asset_id, beat_asset_id, vocals_asset_id?, voice…, vocal_gain_db, beat_gain_db, title }` or `{ mode: "model", lyrics_asset_id, style_prompt, duration_seconds }` |

Vocals are spoken lines placed one per bar after a two-bar lead-in; `meta.line_timings` holds each line's start
and end. In mix mode a missing vocal track is generated and stored as its own asset; the beat and lyrics are
never regenerated. The beat is looped under the vocals and the mix is normalized to −14 LUFS.

## Videos and artwork

| Method | Path | Body |
| --- | --- | --- |
| POST | `/api/videos/generate` | `{ audio_asset_id?, lyrics_asset_id?, style, aspect: 16:9\|9:16\|1:1, subtitles, duration_seconds? (no audio), notes, title }` |
| POST | `/api/artwork/generate` | `{ title, genre, mood, style, character, notes, lyrics_asset_id? }` → 1024×1024 PNG |

A video job also stores a `storyboard` asset (`content.source`: `llm` or `template`). Scene cuts follow the
song's sections, using the vocal timings when present.

## Voice profiles

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/voices` | Profiles: name, owner, consent statement and time, `usable` |
| POST | `/api/voices` | Multipart: `file` (5 s – 5 min), `name`, `owner_name`, `consent_statement`, `consent_confirmed=true`. Rejected with `consent_required` otherwise |
| DELETE | `/api/voices/{id}` | Removes the profile, the sample and the provider's copy |
| GET | `/api/voices/{id}/sample` | The private sample (auth or signed token) |
| GET | `/api/voices/stock` | The active provider's voices and `speech/singing/cloning/conversion` flags |

## System and Model Settings

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | `{ status, auth_required }`. Always open |
| GET | `/api/system/capabilities` | What serves each kind right now |
| GET | `/api/system/providers` | Per kind: active provider, model, URL, `has_api_key`, source, error, and every option with hardware, licence, params, `verified`, `missing_packages`. Never returns keys |
| PUT | `/api/system/providers/{kind}` | `{ provider, model, base_url, api_key, enabled }`. Validated before saving; omit `api_key` to keep the stored one |
| DELETE | `/api/system/providers/{kind}` | Forget the setting, fall back to `.env` |
| POST | `/api/system/providers/{kind}/check` | Live connectivity check |
| GET | `/api/system/hardware` | FFmpeg, GPUs (nvidia-smi), installed packages |
| GET | `/api/meta/options` | Option lists for the UI |

## Projects

| Method | Path | Purpose |
| --- | --- | --- |
| GET, POST | `/api/projects` | List / create `{ name, description }` |
| GET, PATCH, DELETE | `/api/projects/{id}` | Read / rename / delete with every asset and file |
| POST | `/api/projects/{id}/duplicate` | Deep copy, files included |
| GET | `/api/projects/{id}/assets`, `/jobs` | Contents and history |
| GET | `/api/projects/{id}/export` | Zip: manifest, lyrics as text, latest media files |
