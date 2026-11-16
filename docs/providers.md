# Providers and model research

## Configuring the text provider

| Variable | Meaning |
| --- | --- |
| `TROLL_LLM_PROVIDER` | `none` (default), `ollama`, `openai`, `openai_compatible`, `mock` |
| `TROLL_LLM_BASE_URL` | API root ending in `/v1`. Preset for `ollama` and `openai` |
| `TROLL_LLM_MODEL` | Model name. Defaults to `llama3.2` for `ollama`; required otherwise |
| `TROLL_LLM_API_KEY` | Required for `openai`; optional elsewhere |
| `TROLL_LLM_TIMEOUT` | Seconds, default 120 |
| `TROLL_LLM_JSON_MODE` | `true` sends `response_format: json_object`. Helps small models; not every server accepts it |

All three real options use one adapter, `OpenAICompatibleProvider`, which calls `POST /chat/completions`.
The `openai` preset sends `max_completion_tokens` and omits `temperature`, because current OpenAI models
reject the older parameters.

Lyrics quality depends heavily on the model. Small local models sometimes return malformed JSON; the
service retries once and then fails the job with a clear message instead of saving garbage.

## Writing an adapter

1. Subclass the interface in `troll_music_ai/providers/base.py`.
2. Implement `info`, `check()` (must not raise) and the generation method.
3. Raise `ProviderUnavailableError` for network problems and `ProviderResponseError` for bad answers. Never
   put credentials in an error message.
4. Add it to the factory in `troll_music_ai/config.py` and document its variables in `.env.example`.
5. Test it against a fake transport, as in `tests/test_openai_compatible_provider.py`.

## Candidate models for the planned modules

> **Read this first.** The table below is a starting point for contributors, written from the maintainers'
> notes in November 2026. **None of these integrations exist yet and none of these claims have been
> re-verified against the upstream repositories.** Licences and capabilities change. Check the upstream
> licence file and model card before writing an adapter, and again before any commercial use.

| Technology | Would serve | Capability notes | Licence notes (verify) | Hardware |
| --- | --- | --- | --- | --- |
| **Ollama** | Text | Local LLM runner with an OpenAI-compatible `/v1` API. Already supported | MIT for Ollama; each model has its own licence | CPU works, GPU recommended |
| **ACE-Step** | Music, full songs | Text-and-lyrics to music, including sung vocals and instrumentals. The strongest open candidate for both the beat and song modules | Reported as Apache-2.0 | GPU with several GB of VRAM |
| **Stable Audio Open** | Music (instrumental) | Short stereo clips (under a minute). Better for loops and sound design than full songs. No vocals | Stability AI Community Licence: restrictions on commercial use above a revenue threshold | GPU recommended |
| **MusicGen (AudioCraft)** | Music (instrumental) | Text to instrumental, optional melody conditioning | Code MIT, **weights CC-BY-NC**: non-commercial | GPU recommended |
| **Chatterbox** | Speech, voice cloning | Zero-shot voice cloning for **speech**. It does not sing | Reported as MIT | GPU recommended, CPU possible |
| **XTTS v2** | Speech, voice cloning | Multilingual speech cloning from a short sample. Speech only | Coqui Public Model Licence: **non-commercial**, and the company no longer sells commercial licences | GPU recommended |
| **RVC / so-vits-svc** | Singing voice (conversion) | Converts an existing sung vocal to a target voice. A realistic path to "my voice, singing": synthesize or record a guide vocal, then convert the timbre. Needs training per voice | Code MIT-style; trained voices carry consent obligations | GPU for training |
| **ComfyUI** | Image, video | A workflow server with an HTTP API. One adapter can cover many image and video models | GPL-3.0 for ComfyUI itself; **each model differs** (some popular image models are non-commercial) | GPU |
| **FFmpeg** | Audio and video processing | Conversion, loudness normalization, mixing, subtitles, rendering. Used as a subprocess, not linked | LGPL or GPL depending on the build | CPU |

### What this means for the design

- **Singing with your own voice is a two-step problem.** No widely available open model turns text plus a
  short voice sample directly into convincing singing. The planned route is a singing provider (such as
  ACE-Step) for the performance, followed by voice conversion to the authorized target voice. That is why
  `SingingVoiceProvider` is separate from `SpeechProvider` and `VoiceCloningProvider`.
- **Licences are part of provider selection.** `MusicCapabilities.commercial_use` exists so the UI can warn
  before someone releases a track made with a non-commercial model.
- **Hosted APIs are first-class.** Every interface is network-friendly, so the studio can run on a laptop
  without a GPU when API providers are configured.
