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

## Troll (one button)

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/api/troll` | The whole meme as one job: lyrics (or battle), vocals, beat, mix, fake album cover, optional vertical MP4. Body: `{"request": TrollRequest, "project_id"?, "with_video"?, "with_cover"?}`. Without `project_id` a project named after the target is created. `202` + job. |
| `POST` | `/api/troll/remix` | Make a finished troll again with `style`, `intensity`, `delivery`, `rapper_name`, `voice` or an `instruction` changed. Reuses the lyrics; a new delivery, intensity or instruction rewrites them first (as a new version). `202` + job. |
| `GET` | `/api/troll/templates` | The 14 roast templates. |
| `GET` | `/api/troll/options` | Kinds, styles, intensities, deliveries and templates. |
| `GET` | `/api/troll/random` | A random situation and settings (no model). |
| `GET` | `/api/troll/rapper-name?target=` | A ridiculous stage name (word list, no model). |

| `POST` | `/api/troll/factory` | Meme Factory: `{"asset_id", "items": [...], "theme", "award"?, "line"?}`. Items: `vertical_video`, `square_video`, `wide_video`, `square_cover` (reuses the troll's cover), `concert_poster`, `award_card`, `streaming_card`, `reaction_meme`. Themes: `neon`, `gold`, `vaporwave`, `grunge`, `comic`. Designs are drawn by Pillow over one background per run and marked `meta.parody`. `202` + job. |

Remix also takes `regenerate_sections` (section ids) and `section_instruction`: only those sections are rewritten
(one person's verse in a group roast, the chorus), then the track is re-performed.

### Roast battles

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/api/battles/{asset_id}?voter_id=` | Rappers, battle lyrics, latest scorecard and vote tally. `asset_id` can be the song, video or lyrics. `404 not_a_battle` otherwise. |
| `POST` | `/api/battles/{asset_id}/score` | The AI judges' opinion: per-rapper marks 1-10 for punchlines, flow, creativity, humor, entertainment, a comment, the winner (or a draw), an announcement and the best line. Stored as a `scorecard` asset with `meta.opinion: true`. `201`. |
| `GET` | `/api/battles/{asset_id}/votes?voter_id=` | `{"counts", "total", "your_vote"}`. |
| `POST` | `/api/battles/{asset_id}/votes` | `{"choice": rapper name or "draw", "voter_id"}`. The same voter id changes its vote. No accounts yet, so this prevents accidental double votes only. |

### Troll Universe and Roast Awards

| Method | Path | What it does |
| --- | --- | --- |
| `GET` / `POST` | `/api/universe/rappers` | List rappers, or create one you wrote (`name`, `personality`, `style`, `delivery`, `catchphrase`, `bio`, `stats`, `voice`). |
| `POST` | `/api/universe/rappers/generate` | `{"idea"?}`: the text model invents a fictional rapper (`origin: "ai"`). With no text model, word lists do (`origin: "builtin"`, not AI). |
| `GET` / `PATCH` / `DELETE` | `/api/universe/rappers/{id}` | Read, edit (the card is reprinted), or retire (their rivalries go too; tracks stay). |
| `POST` | `/api/universe/rappers/{id}/portrait` | Job: a portrait from the image provider, then a new collectible card. |
| `GET` / `POST` | `/api/universe/rivalries` | List, or start one: `{"rapper_a_id", "rapper_b_id", "tagline"}`. Each rivalry gets its own project. |
| `GET` / `DELETE` | `/api/universe/rivalries/{id}` | Rappers, head-to-head record, champion and battle history. |
| `POST` | `/api/universe/rivalries/{id}/tracks` | Job: `{"kind": "battle"}` (both rappers, their voices, Knockout round) or `{"kind": "diss", "from_id"}`; also `style`, `intensity`, `with_video`, `situation`. |
| `POST` | `/api/universe/rivalries/{id}/settle` | `{"song_asset_id", "winner"?}`: a rapper id or `draw`; without it, the friends' votes decide, else the AI judges' scorecard. `422 undecided` if neither exists. Records, titles and cards update. |
| `POST` | `/api/universe/rivalries/{id}/poster` | A rivalry fight poster (Pillow). |
| `POST` | `/api/awards/{asset_id}` | Job: `{"count": 1-4, "theme"}`. The text model picks awards from a fixed list with reasons; each becomes an award card with `meta.judged_by`. |
| `GET` | `/api/awards/{asset_id}` | The award cards made for that track. |

A champion is the first rapper to 3 wins in a rivalry while ahead on wins; the title shows on their card.
Stats (1-99) are invented for fun; wins, losses and titles come only from settled battles.

`POST /api/assets/zip` with `{"asset_ids", "name"}` downloads those files as one ZIP.

`TrollRequest`: `situation` (required), `kind` (`diss_track`, `roast`, `rap_battle`, `meme_song`, `group_roast`,
`funny_beat`, `meme_video`), `style` (`drill`, `trap`, `hip-hop`, `pop`, `country`, `opera`, `techno`, and for beats
`circus`, `8-bit`), `intensity` (`friendly`, `savage`, `brutal`), `delivery` (`cocky`, `hype`, `narrator`, `deadpan`,
`news`, `diva`), `target`, `rapper_name`, `template`, `inside_jokes` (up to 5), `people` (group roast: `name`,
`nickname`, `description`, `voice`), `group_name`, `voice`, `voice_b` (battle), `explicit`, `language`.

The job's `stage` reads `"<step> · <detail>"` where step is one of `Writing the lyrics`, `Recording the vocals`,
`Building the beat`, `Mixing the track`, `Designing the cover`, `Rendering the video`. The finished song (or beat)
carries `meta.troll`: kind, artist, target, settings, the full request, and the ids of the lyrics, cover and video,
plus any warnings (a failed cover does not fail the song).

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

Also:

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/api/lyrics/{id}/punchlines` | Punchline mode: `{"section_id", "line_index", "count": 5, "instruction"?}` returns `{"current", "options", "provider", "model", "is_mock"}`. A direct model call; nothing is saved until you `PUT` the edited lyrics. |
| `POST` | `/api/lyrics/{id}/restore` | Make that older version the newest again (`origin: "restored"`). Every version is kept. |

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
