# Models and providers

Each capability (text, music, voice, image) is served by one provider at a time, chosen in **Model Settings**
or with environment variables (`TROLL_LLM_*`, `TROLL_MUSIC_*`, `TROLL_VOICE_*`, `TROLL_IMAGE_*`). Model
Settings wins over the environment. The registry that defines every option is
[`providers/registry.py`](../packages/python-sdk/src/troll_music_ai/providers/registry.py).

**Status key**

- **Tested live**: run against the real model or service while building this release (see the dates).
- **Mocked only**: the adapter follows the provider's published API and its request/response handling is covered
  by tests with a simulated server, but it has not been run against the real thing. The studio marks these
  "(untested)".
- **Blocked here**: the code path is wired, but the model could not be run on the development machine for the
  stated reason.

Built-in engines are real, deterministic software, not AI. Their output is labelled `is_ai: false`.

## Text (lyrics, battles, storyboards, character ideas)

| Provider | Runs | Default model | Status | Notes |
| --- | --- | --- | --- | --- |
| `pollinations` | hosted, keyless | `openai-fast` (GPT-OSS 20B) | Tested live 2026-11-16 | Rate-limited. Prompts leave your machine. A reasoning model: the preset raises the token budget and sets `reasoning_effort: low`. |
| `ollama` | local | `llama3.2` | Mocked only (Ollama not installed here) | Any model you have pulled. 3B models sometimes return broken JSON; the parser repairs common slips and retries once. |
| `openai_compatible` | either | you choose | Mocked only | LM Studio, vLLM, llama.cpp server, OpenRouter, Groq… |
| `openai` | hosted | you choose | Mocked only | Uses `max_completion_tokens`, no temperature. |
| `mock` | local | n/a | Test double | Placeholder text, labelled as mock. |

## Music (beats, full songs)

| Provider | Runs | Model | Status | Notes |
| --- | --- | --- | --- | --- |
| `procedural` (default) | local, CPU | `troll-synth-1` | Built-in, tested | NumPy drum machine, bass and chords with genre presets. Exact BPM and length, reproducible per seed. Not AI. |
| `musicgen` | local, GPU recommended | `facebook/musicgen-small` (also medium, stereo-small) | **Blocked here**: weights not downloaded | Up to 30 s per pass; longer beats are looped by FFmpeg and marked `looped`. BPM is only a prompt hint (`bpm_exact: false`). **CC-BY-NC 4.0: non-commercial.** Needs `torch`, `transformers`, then `python scripts/download_models.py musicgen` (~2.4 GB). Never downloads on its own (`local_files_only`). |
| `acestep` | your server, CUDA GPU | ACE-Step 1.5 | Mocked only | **Sings lyrics.** Free and local. Run its API server (`uv run acestep-api`, port 8001) in its own Python 3.11–3.12 environment; 8 GB VRAM runs the 2B turbo model with the 0.6B planner. Uses `/release_task` (with `thinking: true` for songs), `/query_result`, `/v1/audio`. |
| `elevenlabs_music` | hosted | `music_v2_5` (also `music_v2`, `music_v1`) | Mocked only | **Sings lyrics.** `POST /v1/music` with a composition plan: one chunk (v2) or section (v1) per lyric section, with its exact lines and a share of the duration. The Music API needs a **paid** plan; every song uses credits. |

### Full songs with AI vocals

When the active music provider can sing (`acestep` or `elevenlabs_music`), every lyric troll (diss track, roast,
meme song, group roast, battle, meme video) goes **lyrics → one call to the singing model → cover (→ video)**.
There is no separate beat, vocal or mix step, and the timeline shows only "Performing the song" for that part,
because that is what really happens. The style sent to the model comes from the genre, flavour, intensity and
the optional singing voice (`vocal_style`: aggressive, deep, playful, comedic, melodic, pop, electronic). These
are prompt directions, not voice presets, and none of them imitates a real artist.

What is and is not guaranteed:

- The model receives the exact lyrics, in order, section by section. **Nothing checks that it sang every word**;
  the song is stored with `lyrics_adherence: "unverified"` and the result page says the singer may change or skip
  words.
- The audio is normalized to -14 LUFS and encoded as 192 kbps MP3, and a reply shorter than 3 s is rejected.
- If the singer fails (bad key, no paid plan, rate limit after two retries, server down), the troll still
  finishes with **spoken vocals over the built-in beat**, and a warning on the result says why. Timeouts are not
  retried, because a timed-out request may already have been charged.
- Without a singing provider the spoken pipeline is unchanged and labelled "Spoken, not sung".

Setup, cheapest first:

1. **ACE-Step (free, local GPU).** `git clone https://github.com/ace-step/ACE-Step-1.5`, then `uv sync` and
   `uv run acestep-api` in that folder (weights download on first run). Set `TROLL_MUSIC_PROVIDER=acestep`
   (or choose it in AI Settings).
2. **ElevenLabs Music (paid).** Create an API key with music access on a paid plan, then set
   `TROLL_MUSIC_PROVIDER=elevenlabs_music` and `TROLL_MUSIC_API_KEY`. Optional: `TROLL_MUSIC_MODEL=music_v1`.

### Providers considered (November 2026)

| Option | Sings / raps | Official API | Cost | Verdict |
| --- | --- | --- | --- | --- |
| ElevenLabs Music | Yes; v2/v2.5 are documented as handling fast rap | Yes, `POST /v1/music`, lyrics per section | Paid plans only, credits per song | **Integrated** (hosted choice) |
| ACE-Step 1.5 | Yes, sings supplied lyrics | Local API server (MIT code) | Free; needs a GPU | **Integrated** (free local choice) |
| MiniMax Music | Yes | Was official; MiniMax closed the paid music API to new users on 20 Aug 2026 and discontinued the free tier | n/a | Not integrated |
| Suno, Udio | Yes | No official public API | n/a | Not integrated (no unofficial endpoints) |
| Stable Audio | Instrumentals; not a lyrics-to-song model | Yes | Paid | Not suitable for vocals |
| MusicGen | Instrumentals only | Local | Free (CC-BY-NC weights) | Already integrated for beats |

## Voice (vocals, voice profiles)

No voice provider here sings. Vocals are spoken lines placed on the beat grid, labelled `delivery: spoken`.

| Provider | Runs | Capabilities | Status | Notes |
| --- | --- | --- | --- | --- |
| `system_tts` (default) | local | speech | Tested live 2026-11-16 (Windows SAPI: David, Zira) | pyttsx3 in a subprocess. Linux needs `espeak-ng`. Not AI. |
| `openai_speech` | either | speech | Mocked only | Any `/audio/speech` server: OpenAI `gpt-4o-mini-tts`, Kokoro-FastAPI, LocalAI. |
| `elevenlabs` | hosted | speech, cloning, conversion | Mocked only | Instant voice cloning (`/v1/voices/add`) only from a consented profile; speech-to-speech conversion keeps the timing and melody of an existing vocal. |
| `chatterbox` | local, GPU | speech, zero-shot cloning | Mocked only (package not installed) | `pip install chatterbox-tts`; weights (~2 GB) download on first use, so the studio says so before you pick it. |

## Images (cover art, video scenes)

| Provider | Runs | Model | Status | Notes |
| --- | --- | --- | --- | --- |
| `typographic` (default) | local | `troll-cards-1` | Built-in, tested | Gradient title cards drawn with Pillow. Ignores style prompts. Not AI. |
| `pollinations` | hosted, keyless | `flux` | Tested live 2026-11-16 | Free tier: about one image per 45 s per IP; the adapter retries, and a video falls back to title cards for scenes that still fail (counted in the video's metadata). |
| `openai_images` | either | `gpt-image-1` | Mocked only | Any `/images/generations` server. |
| `comfyui` | your server, GPU | a checkpoint file name | Mocked only | Standard text-to-image graph; set the model to e.g. `sd_xl_base_1.0.safetensors`. |

## Video

No AI video-animation model is integrated. Music videos are rendered by FFmpeg from one image per storyboard
scene (slow pan/zoom, fades), with the song's audio and, when available, lyrics burned in at the exact times the
lines are performed. Output: H.264/AAC MP4 in 16:9 (1280×720), 9:16 (720×1280) or 1:1 (1024×1024).

## Hardware

Everything built-in runs on any CPU. For local AI: MusicGen-small wants ~4 GB VRAM (medium ~8 GB+); ACE-Step
1.5 a CUDA GPU with ~5 GB of weights; Chatterbox ~6 GB VRAM; ComfyUI with SDXL ~8 GB. Model Settings shows the
backend's GPU, FFmpeg and installed packages.

## Adding a provider

Implement the interface in [`providers/base.py`](../packages/python-sdk/src/troll_music_ai/providers/base.py),
then `register(ProviderSpec(...))` in the registry with honest `capabilities`, `params`, `hardware`, `license`
and `verified=False` until you have run it for real. It appears in Model Settings automatically.
