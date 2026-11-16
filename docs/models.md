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
| `acestep` | your server, CUDA GPU | ACE-Step 1.5 | Mocked only | The only option that **sings lyrics** (Song page, "Sung by a music model"). Run its API server (`uv run acestep-api`, port 8001) in its own Python 3.11–3.12 environment. Uses `/release_task`, `/query_result`, `/v1/audio`. |
| `elevenlabs_music` | hosted | `music_v1` | Mocked only | `POST /v1/music` with `force_instrumental`. Needs a plan with Music. |

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
