# troll-music-ai (Python toolkit)

The generation core of TROLL-MUSIC-AI: provider registry and adapters, the lyrics engine, the built-in
beat engine, and a REST client for the backend. It depends on `pydantic`, `httpx` and `numpy`; optional
extras: `[images]` (Pillow), `[speech]` (pyttsx3), `[musicgen]` (torch, transformers).

```bash
pip install -e packages/python-sdk
```

## Lyrics

```python
from troll_music_ai import LLMConfig, TrollMusic

# Reads TROLL_LLM_* from the environment, or configure explicitly:
studio = TrollMusic(llm=LLMConfig(provider="ollama", model="llama3.2"))

status = studio.check_text_provider()
print(status.ok, status.detail)

lyrics = studio.generate_lyrics(
    prompt="A funny diss track about a fake millionaire",
    genre="drill",
    style="diss_track",
    troll_intensity=4,
    verses=2,
)

for section in lyrics.sections:
    print(f"[{section.label}]", *section.lines, sep="\n")

print(lyrics.suggested_bpm, lyrics.beat_notes)
open("song.md", "w", encoding="utf-8").write(lyrics.to_markdown())
```

Refine without regenerating everything:

```python
verse = lyrics.sections[1]
lyrics = studio.regenerate_section(lyrics, verse.id, instruction="add a yacht")
lyrics = studio.rewrite_lyrics(lyrics, "funnier")
lyrics = studio.rewrite_lyrics(lyrics, "rhyme_scheme", rhyme_scheme="ABAB")
```

Each call returns a new `Lyrics` object; the input is not modified.

## Async

```python
import asyncio
from troll_music_ai import AsyncTrollMusic

async def main():
    studio = AsyncTrollMusic()
    lyrics = await studio.generate_lyrics("My cat judging my life choices", genre="lo-fi")
    print(lyrics.to_text())

asyncio.run(main())
```

Use `AsyncTrollMusic` inside anything that already runs an event loop (FastAPI, notebooks).

## Typed requests

```python
from troll_music_ai import LyricsRequest, LyricStyle, TrollMusic

request = LyricsRequest(prompt="Monday meetings", style=LyricStyle.SARCASTIC, explicit=False)
lyrics = TrollMusic().generate_lyrics(request=request)
```

## Errors

Everything derives from `TrollMusicError` and has a stable `.code`.

| Error | When |
| --- | --- |
| `ProviderNotConfiguredError` | No provider selected, or its settings are incomplete |
| `ProviderUnavailableError` | The provider cannot be reached or timed out |
| `ProviderResponseError` | The provider answered with an error (`.status_code`) |
| `LyricsParseError` | The model's output could not be turned into lyrics, after a retry |
| `FeatureNotAvailableError` | The module has no adapter yet |

## Beats without a server

```python
path = TrollMusic().generate_beat("beat.wav", genre="drill", bpm=140, duration_seconds=30)
```

Uses `TROLL_MUSIC_PROVIDER` (default: the built-in synthesizer, which is not an AI model). Vocals, songs and
videos are assembled by the backend with FFmpeg, so `generate_vocals`, `generate_song` and
`generate_music_video` on the local toolkit raise `FeatureNotAvailableError` pointing you to the REST client.

## REST client

With a running backend, `TrollMusic(api_key=..., base_url=...)` returns a `TrollMusicClient`:

```python
from troll_music_ai import TrollMusic, JobFailedError

client = TrollMusic(api_key=None, base_url="http://localhost:8000")
lyrics = client.generate_lyrics("my landlord", genre="drill")          # -> Asset (kind "lyrics")
beat = client.generate_beat(genre="drill", bpm=140, duration_seconds=60)
song = client.generate_song(lyrics, beat, voice="Zira")
video = client.generate_music_video(song, aspect="9:16", style="meme")
cover = client.generate_artwork("Landlord Blues", genre="drill", style="retro")
client.download(song, "song.mp3")

print(song.meta["delivery"], song.is_ai, song.provider)   # honest provenance on every asset

try:
    client.generate_beat(genre="phonk")
except JobFailedError as error:
    print(error.code, error.job.error)
```

Also: `import_lyrics`, `generate_battle`, `generate_vocals`, `upload_audio`, `create_voice_profile`
(requires `consent_confirmed=True` and the owner's statement), `list_voice_profiles`, `stock_voices`,
`providers`, `check_provider`, `get_job`, `cancel_job`, `retry_job`, `wait_for_job`, `list_assets`.
Every generation method takes `wait=False` (return the job) and `on_progress=callback`.
`AsyncTrollMusicClient` has the same methods as coroutines. `TROLL_API_URL` and `TROLL_API_KEY` are read
from the environment when not passed.

## One-button trolls

```python
from troll_music_ai import TrollMusicClient

with TrollMusicClient(base_url="http://localhost:8000") as client:
    song = client.troll("Dave acts rich but borrows money every Friday", kind="diss_track",
                        style="trap", intensity="savage", target="Dave", template="broke")
    client.download(song, "dave.mp3")
    print(song.meta["troll"]["artist"], song.meta["troll"]["lyrics_asset_id"])

    opera = client.remix(song, style="opera")             # same lyrics, new beat and cover
    lyrics = client.get_asset(song.meta["troll"]["lyrics_asset_id"])
    ideas = client.punchlines(lyrics, lyrics.lyrics.sections[1].id, 0)   # five alternatives
    print(ideas["options"])
```

Battles, the Meme Factory and group roasts:

```python
battle = client.troll("Marcus only knows one song on guitar", kind="rap_battle", target="Marcus")
card = client.score_battle(battle)          # AI judges' opinion, stored as a scorecard asset
client.vote(battle, "Marcus", voter_id="my-browser-id")

pack = client.meme_factory(battle, ["vertical_video", "concert_poster", "award_card"], theme="gold")
client.download_zip(pack.job.result_asset_ids, "marcus-pack.zip")

group = client.troll("We never book the trip", kind="group_roast",
                     people=[{"name": "Dave", "description": "never pays"}, {"name": "Sam"}])
sam = next(s for s in client.get_asset(group.meta["troll"]["lyrics_asset_id"]).lyrics.sections if s.label == "Sam")
client.remix(group, regenerate_sections=[sam.id])   # only Sam's verse is rewritten
```

Also: `random_troll()`, `templates()`, `battle()`, `save_lyrics()`, `asset_history()`, `restore_lyrics_version()`.

## Your own provider

```python
from troll_music_ai import TrollMusic
from troll_music_ai.providers import TextGenerationProvider

class MyProvider(TextGenerationProvider):
    ...  # implement info, check() and generate_text()

studio = TrollMusic(text_provider=MyProvider())
```
