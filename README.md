# TROLL-MUSIC-AI

**Roast it. Rap it. Release it.**

Turn your friends' funniest moments into diss tracks, roasts, rap battles, meme songs and meme videos, then send
them to the group chat.

Open the app, type what your friend did, pick a type, a style and how hard to go, and press **Generate**. You get
a mixed track, a fake album cover and, for meme videos, a vertical MP4, with synced lyrics you can share,
download, remix or edit line by line.

- **One button, seven formats:** Diss Track, Savage Roast, Rap Battle, Meme Song, Group Chat Roast, Funny Beat,
  Meme Video.
- **Roast templates:** 14 friend archetypes (The Broke Friend, The Group Chat Ghost, ...) that pre-fill the form.
- **Remix:** change the style, heat, delivery, rapper name or voice and make it again, reusing the lyrics.
- **Punchline mode:** pick any line in the Lyrics Editor and get five sharper alternatives. Every edit is a new
  version you can restore.
- **Group Chat Roast ("Everyone gets cooked"):** 2 to 8 people with nicknames, their "crimes" and a voice each;
  one verse per person and a group anthem. Re-cook one person's verse without touching the rest.
- **Roast Battles:** you vs them with two voices, a dramatic intro and a Knockout round; an AI judges'
  scorecard (punchlines, flow, creativity, humor, entertainment) shown as an opinion, and friend voting.
- **Meme Factory:** 9:16 / 1:1 / 16:9 videos (Stories, TikTok, Shorts), the cover, a fake concert poster, a fake
  award from "The Trollies", a parody "now playing" card and a reaction meme, in 5 themes, downloadable as a ZIP.
- **Troll Universe:** invent fictional rappers (by AI from an idea, or from word lists without one) with stats,
  a catchphrase, a bio, a portrait and a collectible card; start rivalries, run battles and diss tracks between
  them, settle results (votes first, then the AI judges) and crown a champion at 3 wins. Private to you.
- **Roast Awards:** the text model gives a track awards from a fixed list ("Most Emotional Damage", ...) with a
  reason quoting the lyrics; each becomes a shareable award card, labelled as an AI opinion.
- **Workshop:** the individual tools (lyrics, beats, songs, voices, videos, covers, battles) for hand-tuning.

Under the hood: a **Python toolkit** (`troll_music_ai`) with a provider registry, the lyrics engine and a REST
client; a **FastAPI backend** that runs generation as background jobs and processes media with FFmpeg; and a
**Next.js app**.

The jokes target what people *do*, never who they *are*: the prompts forbid jokes about looks, health, race,
religion, gender, sexuality or disability, and private details. See [docs/safety.md](docs/safety.md).

## What works, honestly

Every module produces a real file you can play and download, with **no GPU and no API key**, because each
capability has a built-in engine. Those engines are **not AI models**, and the studio labels them so. Plug in an
AI provider per capability in Model Settings or `.env`.

| Module | Built-in engine (default, not AI) | AI providers you can switch to |
| --- | --- | --- |
| Lyrics, rap battles, storyboards | none: needs a text model | **Pollinations** (free, keyless, tested), **Ollama** (local), OpenAI, any OpenAI-compatible API |
| Beats | NumPy drum machine and synth: exact BPM and length | **MusicGen** (local, weights download is manual), **ACE-Step 1.5** (local server, sings lyrics), ElevenLabs Music |
| Vocals | OS speech engine (pyttsx3) | OpenAI-compatible speech (OpenAI, Kokoro), **ElevenLabs** (cloning, voice conversion), Chatterbox (local cloning) |
| Cover art, video scenes | Typographic title cards (Pillow) | **Pollinations** images (tested), OpenAI-compatible images, ComfyUI |
| Song | FFmpeg mix of your beat and vocals, or a full sung song from ACE-Step | |
| Music video | FFmpeg: scene stills with motion, fades, audio and burned-in synced lyrics → MP4 | no AI video-animation model is integrated |

What "tested" means here, and what has not been run against the real service, is spelled out in
[docs/models.md](docs/models.md). Short version: Pollinations text and images and the system speech engine
were run for real; MusicGen needs its weights downloaded first; ACE-Step, ElevenLabs, OpenAI, Chatterbox and
ComfyUI adapters follow their documented APIs and are covered by mocked tests only.

**About vocals.** None of the voice providers sing. Lines are performed as rhythmic speech placed on the beat
grid (one bar per line, sections on even bars), and every vocal asset says `delivery: spoken`. For actually
sung vocals, use ACE-Step's full-song mode.

Also included: projects (duplicate, export a zip with media), version history, uploads of your own beats and
vocals, consent-gated voice profiles, job progress / cancel / retry, optional API-key auth, and a Python SDK.

## Quick start

You need Python 3.11+ and Node.js 20+. FFmpeg is bundled through `imageio-ffmpeg`, so no separate install.

```bash
git clone https://github.com/33martyr/troll-music-ai.git
cd troll-music-ai

python -m venv .venv
.venv/Scripts/activate            # Windows. macOS/Linux: source .venv/bin/activate
pip install -e packages/python-sdk -e ".[dev]"
cp .env.example .env

cd apps/web && npm install && cd ../..
```

Run in two terminals:

```bash
python scripts/dev_backend.py --reload     # API on http://localhost:8000, docs at /docs
```

```bash
npm --prefix apps/web run dev              # Studio on http://localhost:3000
```

Open **Model Settings** and pick a text provider. The quickest is **Pollinations** (free, no key; your prompts
are sent to pollinations.ai). For fully local lyrics, install [Ollama](https://ollama.com), run
`ollama pull llama3.2` and choose Ollama.

`python scripts/dev_backend.py --mock` uses a mock text provider and a separate database. Its output is
placeholder text, labelled as mock everywhere.

### Local AI models

Nothing downloads model weights automatically. To use MusicGen on your GPU:

```bash
pip install -e ".[musicgen]"              # torch + transformers; use the CUDA build of torch for your GPU
python scripts/download_models.py musicgen  # about 2.4 GB, CC-BY-NC (non-commercial)
```

Then choose MusicGen in Model Settings. See [docs/models.md](docs/models.md) for ACE-Step, Chatterbox and ComfyUI.

## Python SDK

Against a running backend:

```python
from troll_music_ai import TrollMusic

client = TrollMusic(api_key="your-api-key", base_url="http://localhost:8000")  # api_key only if TROLL_API_KEY is set

lyrics = client.generate_lyrics("my flatmate never does the dishes", genre="drill")
beat = client.generate_beat(genre="drill", bpm=140, duration_seconds=60)
song = client.generate_song(lyrics, beat)
video = client.generate_music_video(song, aspect="9:16", style="meme")
client.download(video, "video.mp4")
```

Every call waits for its job and returns a typed `Asset`; pass `wait=False` to get the `JobInfo`. Errors are
typed (`ApiError`, `AuthenticationError`, `JobFailedError`, `JobTimeoutError`). `AsyncTrollMusicClient` has the
same methods as coroutines.

Without a server, `TrollMusic()` is the in-process toolkit: lyrics with your LLM and beats with the configured
music provider (`studio.generate_beat("beat.wav", genre="trap", bpm=140)`). More in
[packages/python-sdk/README.md](packages/python-sdk/README.md) and [examples/](examples/).

## Tests

```bash
pytest                                            # mocked providers, real FFmpeg and audio
TROLL_RUN_INTEGRATION=1 pytest tests/integration -v -rs   # calls real providers, skips what is unavailable
```

The default suite runs real media processing (the beat engine, mixing, video rendering) but never calls an AI
service. Integration tests skip, with the reason, whatever is not available on your machine. A skip is not a pass.

## Documentation

- [Models and providers](docs/models.md): every integration, what it needs, its licence, what was tested
- [Architecture](docs/architecture.md): components, schema, jobs, storage, media pipeline
- [REST API](docs/api.md)
- [Roadmap](docs/roadmap.md)
- [Safety and privacy](docs/safety.md)
- [Docker](docker/README.md)

## Repository layout

```
apps/web/               Next.js studio
backend/                FastAPI app: api, audio, core, models, services, video, workers
packages/python-sdk/    troll_music_ai: types, providers + registry, lyrics, REST client
tests/                  unit and API tests; tests/integration for real providers
docs/  examples/  docker/  scripts/
```

## Responsible use

This is a comedy tool for jokes about situations, behaviour and fictional characters, not for harassing people.
Voice profiles require the voice owner's explicit, recorded consent, and samples are never served publicly.
See [docs/safety.md](docs/safety.md).

## Licence

[MIT](LICENSE). Models and services you connect have their own licences (MusicGen weights are non-commercial);
check [docs/models.md](docs/models.md) before releasing anything commercially.
