"""Lyrics → beat → song → video → cover with a running backend.

    python scripts/dev_backend.py            # in another terminal
    python examples/full_song.py "my flatmate never does the dishes"

Choose a text provider in Model Settings first (Pollinations needs no key).
Set TROLL_API_KEY if the backend has one.
"""

from __future__ import annotations

import sys
from pathlib import Path

from troll_music_ai import JobFailedError, TrollMusic


def progress(job) -> None:
    print(f"\r  {job.status:<10} {job.progress:>4.0%}  {job.stage[:60]:<60}", end="", flush=True)


def main() -> None:
    topic = " ".join(sys.argv[1:]) or "the office printer that only breaks before deadlines"
    out = Path("output")
    with TrollMusic(base_url="http://localhost:8000") as client:
        try:
            print("Lyrics");  lyrics = client.generate_lyrics(topic, genre="trap", length="short", on_progress=progress)
            print(f"\n  {lyrics.title} (by {lyrics.provider}/{lyrics.model}{', MOCK' if lyrics.is_mock else ''})")
            bpm = lyrics.lyrics.suggested_bpm or 140
            print("Beat");    beat = client.generate_beat(genre="trap", bpm=bpm, duration_seconds=30, lyrics=lyrics, on_progress=progress)
            print("\nSong");  song = client.generate_song(lyrics, beat, on_progress=progress)
            print(f"\n  vocals delivery: {song.meta.get('delivery')}")
            print("Video");   video = client.generate_music_video(song, aspect="9:16", style="meme", on_progress=progress)
            print("\nCover"); cover = client.generate_artwork(lyrics.title, genre="trap", style="cartoon", on_progress=progress)
        except JobFailedError as error:
            sys.exit(f"\nFailed ({error.code}): {error}")
        for asset, name in ((song, "song.mp3"), (video, "video.mp4"), (cover, "cover.png")):
            print("\nSaved", client.download(asset, out / name), end="")
        print()


if __name__ == "__main__":
    main()
