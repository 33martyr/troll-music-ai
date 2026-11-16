# Docker

> **Not tested yet.** These files were written alongside the application but have not been built or run by
> the maintainers. Expect to fix small things, and please send a pull request when you do.

```bash
cp .env.example .env        # choose a text provider
docker compose up --build
```

- Studio: http://localhost:3000
- API docs: http://localhost:8000/docs

The stack is PostgreSQL, the backend and the web app. Redis is not included because the job queue is still
in-process. The image includes FFmpeg and espeak-ng, so the built-in beat, speech, image and video engines
work inside it. There is no GPU profile: local AI models (MusicGen, ACE-Step, ComfyUI) are not installed in
the image; run them on the host and point the backend at them, e.g.
`TROLL_MUSIC_BASE_URL=http://host.docker.internal:8001` for ACE-Step.

**Ollama on the host:** set `TROLL_LLM_BASE_URL=http://host.docker.internal:11434/v1` in `.env`.

**Before deploying anywhere public:** change `POSTGRES_PASSWORD`, and put the app behind authentication.
The application has none of its own yet.
