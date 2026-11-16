# Roadmap

Status is updated when work is merged and tested, not when it is planned. "Mocked only" means covered by tests
with a simulated provider but not run against the real service. See [models.md](models.md).

## Done

- [x] Foundation: toolkit and backend packages, schema with version lineage and provenance, projects, jobs
- [x] Lyrics: generate, regenerate a section, rewrite, edit with history, export, **import pasted lyrics**
- [x] Provider registry with Model Settings (per-capability provider, model, URL, key, enable, live check)
- [x] Text: Pollinations (tested live), Ollama, OpenAI, OpenAI-compatible
- [x] Beats: built-in engine (exact BPM), MusicGen, ACE-Step, ElevenLabs Music; variations; uploads
- [x] FFmpeg pipeline: validation, conversion, loop/trim/fade, −14 LUFS loudness, MP3, mixing
- [x] Vocals: speech providers placed on the beat grid with line timings; battle performers get two voices
- [x] Voice profiles: consent required and recorded, private samples, deletion everywhere; cloning and conversion via ElevenLabs/Chatterbox
- [x] Songs: mix mode reusing existing parts; full sung songs via ACE-Step
- [x] Music videos: storyboard (LLM or template), scene images, FFmpeg render with synced subtitles, MP4
- [x] Rap battles with two fictional characters, character suggestions
- [x] Cover art
- [x] Jobs: cancel, retry, interrupted-job recovery; local file storage with download and deletion
- [x] Optional API-key auth with signed media URLs
- [x] SDK REST client (sync and async) with typed results and errors
- [x] Integration tests for real providers (opt-in)

## Next

- [ ] Run the mocked-only adapters against the real services (ACE-Step, ElevenLabs, OpenAI, Chatterbox, ComfyUI) and MusicGen with downloaded weights
- [ ] A singing-voice path for user voices (e.g. ACE-Step output + voice conversion, or a dedicated SVS model)
- [ ] Optional image-to-video model for animated scenes
- [ ] Redis-backed worker for long jobs; streaming progress (SSE)
- [ ] S3-compatible storage
- [ ] Alembic migrations (today `create_all` does not alter existing tables)
- [ ] User accounts and per-user privacy
- [ ] Tested Docker deployment with an optional GPU profile; frontend tests; CI
